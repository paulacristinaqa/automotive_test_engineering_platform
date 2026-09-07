import hashlib
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.models import AdasPerceptionResult, AdasTestScenarioExecution, AdasWorldScene
from atep.adas.planning_service import evaluate_plan
from atep.adas.schemas import (
    AdasFaultType,
    AdasScenarioAssertion,
    AdasScenarioCoverage,
    AdasScenarioExecute,
    AdasScenarioResponse,
    PerceptionPrediction,
    PlanningEvaluationCreate,
    ScenarioStatus,
)
from atep.audit.service import record_audit
from atep.core.errors import (
    AdasScenarioConflictError,
    AdasScenarioContractError,
    AdasSceneVersionConflictError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def scenario_response(
    execution: AdasTestScenarioExecution,
    *,
    scene: AdasWorldScene,
    perception: AdasPerceptionResult,
    duplicate: bool = False,
) -> AdasScenarioResponse:
    return AdasScenarioResponse(
        id=execution.id,
        execution_id=execution.execution_id,
        scene_id=scene.scene_id,
        perception_result_id=perception.result_id,
        scenario_type=execution.scenario_type,
        scene_revision=execution.scene_revision,
        status=execution.status,
        duplicate=duplicate,
        maneuver=execution.maneuver,
        alerts=execution.alerts,
        assertions=execution.assertions,
        fault_injections=execution.fault_injections,
        coverage=execution.coverage,
        regression_fingerprint=execution.regression_fingerprint,
        requested_by_user_id=execution.requested_by_user_id,
        created_at=execution.created_at,
    )


async def require_scenario_execution(
    session: AsyncSession, *, scene_id: UUID, execution_id: str
) -> AdasTestScenarioExecution:
    execution = await session.scalar(
        select(AdasTestScenarioExecution).where(
            AdasTestScenarioExecution.scene_id == scene_id,
            AdasTestScenarioExecution.execution_id == execution_id,
        )
    )
    if execution is None:
        raise ResourceNotFoundError("adas_test_scenario")
    return execution


async def list_scenario_executions(
    session: AsyncSession,
    *,
    scene_id: UUID,
    perception_result_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[AdasTestScenarioExecution], int]:
    filters = (
        AdasTestScenarioExecution.scene_id == scene_id,
        AdasTestScenarioExecution.perception_result_id == perception_result_id,
    )
    total = await session.scalar(
        select(func.count()).select_from(AdasTestScenarioExecution).where(*filters)
    )
    items = list(
        await session.scalars(
            select(AdasTestScenarioExecution)
            .where(*filters)
            .order_by(
                AdasTestScenarioExecution.created_at.desc(),
                AdasTestScenarioExecution.execution_id,
            )
            .limit(limit)
            .offset(offset)
        )
    )
    return items, total or 0


async def execute_scenario(
    session: AsyncSession,
    *,
    scene: AdasWorldScene,
    perception: AdasPerceptionResult,
    command: AdasScenarioExecute,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AdasTestScenarioExecution, bool]:
    request_hash = _sha256(command.model_dump(mode="json"))
    existing = await session.scalar(
        select(AdasTestScenarioExecution).where(
            AdasTestScenarioExecution.scene_id == scene.id,
            AdasTestScenarioExecution.execution_id == command.execution_id,
        )
    )
    if existing is not None:
        if existing.request_hash == request_hash:
            return existing, True
        raise AdasScenarioConflictError()
    if scene.revision != command.expected_scene_revision:
        raise AdasSceneVersionConflictError(
            expected=command.expected_scene_revision, actual=scene.revision
        )
    if perception.scene_revision != scene.revision:
        raise AdasSceneVersionConflictError(
            expected=perception.scene_revision, actual=scene.revision
        )

    original_predictions = [
        PerceptionPrediction.model_validate(item) for item in perception.predictions
    ]
    predictions = _inject_faults(original_predictions, command)
    planning_command = PlanningEvaluationCreate(
        evaluation_id=command.execution_id,
        expected_scene_revision=command.expected_scene_revision,
        ego_lane_id=command.ego_lane_id,
        minimum_following_distance_m=command.minimum_following_distance_m,
        collision_warning_ttc_s=command.collision_warning_ttc_s,
        emergency_brake_ttc_s=command.emergency_brake_ttc_s,
        lane_departure_margin_m=command.lane_departure_margin_m,
    )
    _metrics, maneuver, alerts = evaluate_plan(
        scene=scene, predictions=predictions, command=planning_command
    )
    observed_alerts = {item.alert_type for item in alerts}
    assertions = [
        AdasScenarioAssertion(
            name="expected_maneuver",
            passed=maneuver == command.expected_maneuver,
            expected=command.expected_maneuver.value,
            observed=maneuver.value,
        ),
        AdasScenarioAssertion(
            name="required_alerts",
            passed=set(command.required_alerts) <= observed_alerts,
            expected=",".join(sorted(item.value for item in command.required_alerts)) or "none",
            observed=",".join(sorted(item.value for item in observed_alerts)) or "none",
        ),
        AdasScenarioAssertion(
            name="minimum_overall_f1",
            passed=float(perception.overall_score.get("f1_score", 0)) >= command.minimum_overall_f1,
            expected=f">={command.minimum_overall_f1:.6f}",
            observed=f"{float(perception.overall_score.get('f1_score', 0)):.6f}",
        ),
    ]
    passed_count = sum(item.passed for item in assertions)
    coverage = AdasScenarioCoverage(
        scenario_type=command.scenario_type,
        target_types=sorted(
            {item.target_type for item in predictions}, key=lambda item: item.value
        ),
        alert_types=sorted(observed_alerts, key=lambda item: item.value),
        maneuver=maneuver,
        fault_types=sorted(
            {item.fault_type for item in command.fault_injections}, key=lambda item: item.value
        ),
        assertions_passed=passed_count,
        assertions_total=len(assertions),
        assertion_coverage=round(passed_count / len(assertions), 6),
    )
    deterministic_evidence = {
        "scenario_type": command.scenario_type,
        "scene_revision": scene.revision,
        "predictions": [item.model_dump(mode="json") for item in predictions],
        "planner": planning_command.model_dump(mode="json", exclude={"evaluation_id"}),
        "maneuver": maneuver,
        "alerts": [item.model_dump(mode="json") for item in alerts],
        "assertions": [item.model_dump(mode="json") for item in assertions],
        "coverage": coverage.model_dump(mode="json"),
    }
    execution = AdasTestScenarioExecution(
        scene_id=scene.id,
        perception_result_id=perception.id,
        execution_id=command.execution_id,
        scenario_type=command.scenario_type.value,
        scene_revision=scene.revision,
        request_hash=request_hash,
        status=(
            ScenarioStatus.PASSED
            if passed_count == len(assertions)
            else ScenarioStatus.FAILED
        ).value,
        maneuver=maneuver.value,
        alerts=[item.model_dump(mode="json") for item in alerts],
        assertions=[item.model_dump(mode="json") for item in assertions],
        fault_injections=[item.model_dump(mode="json") for item in command.fault_injections],
        coverage=coverage.model_dump(mode="json"),
        regression_fingerprint=_sha256(deterministic_evidence),
        requested_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(execution)
            await session.flush()
    except IntegrityError as exc:
        raise AdasScenarioConflictError() from exc
    evidence = {
        "scene_id": scene.scene_id,
        "execution_id": execution.execution_id,
        "scenario_type": execution.scenario_type,
        "scene_revision": execution.scene_revision,
        "status": execution.status,
        "assertions_passed": passed_count,
        "assertions_total": len(assertions),
        "fault_count": len(command.fault_injections),
        "regression_fingerprint": execution.regression_fingerprint,
    }
    enqueue_event(
        session,
        event_type="atep.adas.test_scenario.completed.v1",
        aggregate_type="adas_test_scenario",
        aggregate_id=execution.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="adas.test_scenario_completed",
        resource_type="adas_test_scenario",
        resource_id=execution.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return execution, False


def _inject_faults(
    predictions: list[PerceptionPrediction], command: AdasScenarioExecute
) -> list[PerceptionPrediction]:
    by_id = {item.prediction_id: item for item in predictions}
    unknown = {item.prediction_id for item in command.fault_injections} - set(by_id)
    if unknown:
        raise AdasScenarioContractError(
            "fault injections reference unknown predictions: " + ", ".join(sorted(unknown))
        )
    faults = {item.prediction_id: item for item in command.fault_injections}
    output: list[PerceptionPrediction] = []
    for prediction in predictions:
        fault = faults.get(prediction.prediction_id)
        if fault is None:
            output.append(prediction)
        elif fault.fault_type == AdasFaultType.MISCLASSIFY_PREDICTION:
            replacement = fault.replacement_classification
            assert replacement is not None
            output.append(
                prediction.model_copy(update={"classification": replacement})
            )
    return output
