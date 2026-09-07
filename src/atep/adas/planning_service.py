import math
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.models import AdasPerceptionResult, AdasPlanningEvaluation, AdasWorldScene
from atep.adas.schemas import (
    ActorType,
    AdasAlert,
    AdasAlertType,
    AlertSeverity,
    Lane,
    ManeuverType,
    PerceptionPrediction,
    PerceptionTargetType,
    PlanningEvaluationCreate,
    PlanningEvaluationResponse,
    PlanningRiskMetrics,
    WorldActor,
)
from atep.audit.service import record_audit
from atep.core.errors import (
    AdasPlanningConflictError,
    AdasSceneContractError,
    AdasSceneVersionConflictError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event


def planning_response(
    evaluation: AdasPlanningEvaluation,
    perception: AdasPerceptionResult,
    scene: AdasWorldScene,
) -> PlanningEvaluationResponse:
    return PlanningEvaluationResponse(
        id=evaluation.id,
        evaluation_id=evaluation.evaluation_id,
        perception_result_id=perception.result_id,
        scene_id=scene.scene_id,
        scene_revision=evaluation.scene_revision,
        maneuver=evaluation.maneuver,
        risk_metrics=evaluation.risk_metrics,
        alerts=evaluation.alerts,
        requested_by_user_id=evaluation.requested_by_user_id,
        created_at=evaluation.created_at,
    )


async def require_planning_evaluation(
    session: AsyncSession, *, perception_result_id: UUID, evaluation_id: str
) -> AdasPlanningEvaluation:
    evaluation = await session.scalar(
        select(AdasPlanningEvaluation).where(
            AdasPlanningEvaluation.perception_result_id == perception_result_id,
            AdasPlanningEvaluation.evaluation_id == evaluation_id,
        )
    )
    if evaluation is None:
        raise ResourceNotFoundError("adas_planning_evaluation")
    return evaluation


async def create_planning_evaluation(
    session: AsyncSession,
    *,
    scene: AdasWorldScene,
    perception: AdasPerceptionResult,
    command: PlanningEvaluationCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> AdasPlanningEvaluation:
    if scene.revision != command.expected_scene_revision:
        raise AdasSceneVersionConflictError(
            expected=command.expected_scene_revision, actual=scene.revision
        )
    if perception.scene_revision != scene.revision:
        raise AdasSceneVersionConflictError(
            expected=perception.scene_revision, actual=scene.revision
        )
    metrics, maneuver, alerts = evaluate_plan(
        scene=scene,
        predictions=[PerceptionPrediction.model_validate(item) for item in perception.predictions],
        command=command,
    )
    evaluation = AdasPlanningEvaluation(
        perception_result_id=perception.id,
        evaluation_id=command.evaluation_id,
        scene_revision=scene.revision,
        input_parameters=command.model_dump(mode="json"),
        maneuver=maneuver.value,
        risk_metrics=metrics.model_dump(mode="json"),
        alerts=[item.model_dump(mode="json") for item in alerts],
        requested_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(evaluation)
            await session.flush()
    except IntegrityError as exc:
        raise AdasPlanningConflictError() from exc
    evidence = {
        "scene_id": scene.scene_id,
        "perception_result_id": perception.result_id,
        "evaluation_id": evaluation.evaluation_id,
        "scene_revision": evaluation.scene_revision,
        "maneuver": evaluation.maneuver,
        "alert_count": len(alerts),
        "critical_alert_count": sum(item.severity == AlertSeverity.CRITICAL for item in alerts),
    }
    enqueue_event(
        session,
        event_type="atep.adas.planning.evaluation.created.v1",
        aggregate_type="adas_planning_evaluation",
        aggregate_id=evaluation.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="adas.planning_evaluation_created",
        resource_type="adas_planning_evaluation",
        resource_id=evaluation.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return evaluation


def evaluate_plan(
    *,
    scene: AdasWorldScene,
    predictions: list[PerceptionPrediction],
    command: PlanningEvaluationCreate,
) -> tuple[PlanningRiskMetrics, ManeuverType, list[AdasAlert]]:
    actors = [WorldActor.model_validate(item) for item in scene.actors]
    ego = next((item for item in actors if item.actor_type == ActorType.EGO_VEHICLE), None)
    if ego is None:
        raise AdasSceneContractError("The scene requires an ego vehicle for planning.")
    lane = _require_lane(scene, command.ego_lane_id)
    perceived_actor_ids = {
        item.ground_truth_id
        for item in predictions
        if item.target_type in {PerceptionTargetType.OBJECT, PerceptionTargetType.PEDESTRIAN}
    }
    perceived_actors = [item for item in actors if item.actor_id in perceived_actor_ids]
    nearest_lead: float | None = None
    minimum_ttc: float | None = None
    heading = math.radians(ego.heading_deg)
    ego_forward_speed = ego.velocity_mps.x * math.cos(heading) + ego.velocity_mps.y * math.sin(
        heading
    )
    for actor in perceived_actors:
        dx = actor.position_m.x - ego.position_m.x
        dy = actor.position_m.y - ego.position_m.y
        longitudinal = dx * math.cos(heading) + dy * math.sin(heading)
        lateral = -dx * math.sin(heading) + dy * math.cos(heading)
        if longitudinal <= 0 or abs(lateral) > (ego.width_m + actor.width_m) / 2:
            continue
        actor_forward_speed = actor.velocity_mps.x * math.cos(
            heading
        ) + actor.velocity_mps.y * math.sin(heading)
        closing_speed = ego_forward_speed - actor_forward_speed
        if closing_speed > 0:
            ttc = longitudinal / closing_speed
            minimum_ttc = ttc if minimum_ttc is None else min(minimum_ttc, ttc)
        if actor.actor_type == ActorType.VEHICLE:
            nearest_lead = longitudinal if nearest_lead is None else min(nearest_lead, longitudinal)
    lane_offset = _distance_to_polyline(ego.position_m.x, ego.position_m.y, lane)
    allowed_offset = max(0.0, (lane.width_m - ego.width_m) / 2 - command.lane_departure_margin_m)
    lane_departure = lane_offset > allowed_offset
    safe_following = nearest_lead is None or nearest_lead >= command.minimum_following_distance_m
    red_signal = any(
        item.target_type == PerceptionTargetType.SIGNAL and item.classification == "red"
        for item in predictions
    )
    metrics = PlanningRiskMetrics(
        nearest_lead_distance_m=_rounded_optional(nearest_lead),
        minimum_ttc_s=_rounded_optional(minimum_ttc),
        lane_center_offset_m=round(lane_offset, 6),
        safe_following_distance=safe_following,
        lane_departure=lane_departure,
        red_signal_detected=red_signal,
    )
    alerts = _alerts(metrics=metrics, command=command)
    evaluated_ttc = metrics.minimum_ttc_s
    if evaluated_ttc is not None and evaluated_ttc <= command.emergency_brake_ttc_s:
        maneuver = ManeuverType.EMERGENCY_BRAKE
    elif red_signal:
        maneuver = ManeuverType.STOP
    elif (
        evaluated_ttc is not None and evaluated_ttc <= command.collision_warning_ttc_s
    ) or not safe_following:
        maneuver = ManeuverType.BRAKE
    elif lane_departure:
        maneuver = ManeuverType.LANE_CENTERING
    else:
        maneuver = ManeuverType.MAINTAIN_LANE
    return metrics, maneuver, alerts


def _alerts(*, metrics: PlanningRiskMetrics, command: PlanningEvaluationCreate) -> list[AdasAlert]:
    alerts: list[AdasAlert] = []
    if (
        metrics.minimum_ttc_s is not None
        and metrics.minimum_ttc_s <= command.collision_warning_ttc_s
    ):
        severity = (
            AlertSeverity.CRITICAL
            if metrics.minimum_ttc_s <= command.emergency_brake_ttc_s
            else AlertSeverity.WARNING
        )
        alerts.append(
            AdasAlert(
                alert_type=AdasAlertType.FORWARD_COLLISION,
                severity=severity,
                message="Forward collision risk detected.",
            )
        )
    if not metrics.safe_following_distance:
        alerts.append(
            AdasAlert(
                alert_type=AdasAlertType.UNSAFE_FOLLOWING_DISTANCE,
                severity=AlertSeverity.WARNING,
                message="Following distance is below the configured minimum.",
            )
        )
    if metrics.lane_departure:
        alerts.append(
            AdasAlert(
                alert_type=AdasAlertType.LANE_DEPARTURE,
                severity=AlertSeverity.WARNING,
                message="Ego vehicle is outside the permitted lane-center envelope.",
            )
        )
    if metrics.red_signal_detected:
        alerts.append(
            AdasAlert(
                alert_type=AdasAlertType.RED_SIGNAL,
                severity=AlertSeverity.CRITICAL,
                message="A red traffic signal was detected.",
            )
        )
    return alerts


def _require_lane(scene: AdasWorldScene, lane_id: str) -> Lane:
    for road in scene.roads:
        for raw_lane in road["lanes"]:
            lane = Lane.model_validate(raw_lane)
            if lane.lane_id == lane_id:
                return lane
    raise AdasSceneContractError("The planning ego lane does not exist in the scene.")


def _distance_to_polyline(x: float, y: float, lane: Lane) -> float:
    distances: list[float] = []
    for start, end in zip(lane.centerline, lane.centerline[1:], strict=False):
        dx, dy = end.x - start.x, end.y - start.y
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            distances.append(math.hypot(x - start.x, y - start.y))
            continue
        projection = ((x - start.x) * dx + (y - start.y) * dy) / length_squared
        projection = max(0.0, min(1.0, projection))
        distances.append(
            math.hypot(x - (start.x + projection * dx), y - (start.y + projection * dy))
        )
    return min(distances)


def _rounded_optional(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
