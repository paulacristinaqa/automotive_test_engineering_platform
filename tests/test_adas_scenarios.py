from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.models import AdasPerceptionResult, AdasTestScenarioExecution, AdasWorldScene
from atep.adas.scenario_service import execute_scenario
from atep.adas.schemas import AdasScenarioExecute
from atep.audit.models import AuditRecord
from atep.core.errors import (
    AdasScenarioConflictError,
    AdasScenarioContractError,
    AdasSceneVersionConflictError,
)
from atep.events.models import OutboxEvent


class FakeSession:
    def __init__(self, existing: AdasTestScenarioExecution | None = None) -> None:
        self.existing = existing
        self.added: list[Any] = []

    async def scalar(self, _query: Any) -> Any:
        return self.existing

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    @asynccontextmanager
    async def begin_nested(self) -> AsyncIterator[None]:
        yield


def scene(*, revision: int = 5) -> AdasWorldScene:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    dimensions = {
        "heading_deg": 0,
        "length_m": 4.5,
        "width_m": 1.8,
        "height_m": 1.5,
        "trajectory": [],
    }
    return AdasWorldScene(
        id=uuid4(),
        vehicle_id=uuid4(),
        scene_id="ncap-scene-001",
        name="NCAP inspired car-to-car scene",
        coordinate_frame={
            "convention": "ENU",
            "origin_latitude_deg": 0,
            "origin_longitude_deg": 0,
            "origin_altitude_m": 0,
        },
        roads=[
            {
                "road_id": "road-1",
                "lanes": [
                    {
                        "lane_id": "lane-1",
                        "centerline": [{"x": 0, "y": 0, "z": 0}, {"x": 100, "y": 0, "z": 0}],
                        "width_m": 3.5,
                        "speed_limit_kph": 50,
                    }
                ],
            }
        ],
        actors=[
            {
                "actor_id": "ego",
                "actor_type": "ego_vehicle",
                "position_m": {"x": 0, "y": 0, "z": 0},
                "velocity_mps": {"x": 20, "y": 0, "z": 0},
                **dimensions,
            },
            {
                "actor_id": "lead",
                "actor_type": "vehicle",
                "position_m": {"x": 10, "y": 0, "z": 0},
                "velocity_mps": {"x": 0, "y": 0, "z": 0},
                **dimensions,
            },
        ],
        environment={},
        traffic_controls=[],
        revision=revision,
        simulation_time_ms=0,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def perception(world: AdasWorldScene) -> AdasPerceptionResult:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    return AdasPerceptionResult(
        id=uuid4(),
        sensor_observation_id=uuid4(),
        result_id="perception-result-001",
        scene_revision=world.revision,
        model_name="reference",
        model_version="1.0",
        predictions=[
            {
                "prediction_id": "lead-prediction",
                "target_type": "object",
                "ground_truth_id": "lead",
                "classification": "vehicle",
                "confidence": 0.99,
            }
        ],
        overall_score={
            "true_positive": 1,
            "false_positive": 0,
            "false_negative": 0,
            "precision": 1,
            "recall": 1,
            "f1_score": 1,
        },
        scores_by_target={},
        requested_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def command(*, execution_id: str = "ncap-execution-001") -> AdasScenarioExecute:
    return AdasScenarioExecute(
        execution_id=execution_id,
        scenario_type="aeb_car_to_car",
        expected_scene_revision=5,
        ego_lane_id="lane-1",
        expected_maneuver="emergency_brake",
        required_alerts=["forward_collision"],
        minimum_overall_f1=0.9,
    )


def test_scenario_contract_bounds_faults_and_rejects_duplicate_targets() -> None:
    with pytest.raises(ValidationError, match="at most one"):
        AdasScenarioExecute.model_validate(
            {
                **command().model_dump(mode="json"),
                "fault_injections": [
                    {"fault_type": "drop_prediction", "prediction_id": "prediction-1"},
                    {
                        "fault_type": "misclassify_prediction",
                        "prediction_id": "prediction-1",
                        "replacement_classification": "pedestrian",
                    },
                ],
            }
        )
    with pytest.raises(ValidationError, match="requires replacement"):
        AdasScenarioExecute.model_validate(
            {
                **command().model_dump(mode="json"),
                "fault_injections": [
                    {"fault_type": "misclassify_prediction", "prediction_id": "prediction-1"}
                ],
            }
        )


@pytest.mark.asyncio
async def test_ncap_inspired_aeb_scenario_passes_and_persists_minimized_evidence() -> None:
    world = scene()
    fake = FakeSession()
    execution, duplicate = await execute_scenario(
        cast(AsyncSession, fake),
        scene=world,
        perception=perception(world),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert execution.status == "passed"
    assert execution.maneuver == "emergency_brake"
    assert execution.coverage["scenario_type"] == "aeb_car_to_car"
    assert execution.coverage["assertion_coverage"] == 1
    assert len(execution.regression_fingerprint) == 64
    event = next(item for item in fake.added if isinstance(item, OutboxEvent))
    audit = next(item for item in fake.added if isinstance(item, AuditRecord))
    assert event.event_type == "atep.adas.test_scenario.completed.v1"
    assert "alerts" not in event.payload and "predictions" not in event.payload
    assert audit.action == "adas.test_scenario_completed"


@pytest.mark.asyncio
async def test_prediction_drop_fault_produces_repeatable_failed_regression_evidence() -> None:
    world = scene()
    injected = AdasScenarioExecute.model_validate(
        {
            **command().model_dump(mode="json"),
            "fault_injections": [
                {"fault_type": "drop_prediction", "prediction_id": "lead-prediction"}
            ],
        }
    )
    first, _ = await execute_scenario(
        cast(AsyncSession, FakeSession()),
        scene=world,
        perception=perception(world),
        command=injected,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    second_command = AdasScenarioExecute.model_validate(
        {**injected.model_dump(mode="json"), "execution_id": "ncap-execution-002"}
    )
    second, _ = await execute_scenario(
        cast(AsyncSession, FakeSession()),
        scene=world,
        perception=perception(world),
        command=second_command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert first.status == "failed"
    assert first.maneuver == "maintain_lane"
    assert first.coverage["fault_types"] == ["drop_prediction"]
    assert first.regression_fingerprint == second.regression_fingerprint


@pytest.mark.asyncio
async def test_unknown_fault_target_is_rejected_before_writes() -> None:
    world = scene()
    fake = FakeSession()
    invalid = AdasScenarioExecute.model_validate(
        {
            **command().model_dump(mode="json"),
            "fault_injections": [
                {"fault_type": "drop_prediction", "prediction_id": "unknown-prediction"}
            ],
        }
    )
    with pytest.raises(AdasScenarioContractError, match="contract"):
        await execute_scenario(
            cast(AsyncSession, fake),
            scene=world,
            perception=perception(world),
            command=invalid,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert fake.added == []


@pytest.mark.asyncio
async def test_stale_scenario_revision_is_rejected_before_writes() -> None:
    world = scene(revision=6)
    result = perception(world)
    fake = FakeSession()
    with pytest.raises(AdasSceneVersionConflictError):
        await execute_scenario(
            cast(AsyncSession, fake),
            scene=world,
            perception=result,
            command=command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert fake.added == []


@pytest.mark.asyncio
async def test_exact_replay_is_idempotent_and_changed_reuse_conflicts() -> None:
    world = scene()
    original, _ = await execute_scenario(
        cast(AsyncSession, FakeSession()),
        scene=world,
        perception=perception(world),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    exact, duplicate = await execute_scenario(
        cast(AsyncSession, FakeSession(existing=original)),
        scene=world,
        perception=perception(world),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert exact is original and duplicate is True
    changed = AdasScenarioExecute.model_validate(
        {**command().model_dump(mode="json"), "minimum_overall_f1": 0.5}
    )
    with pytest.raises(AdasScenarioConflictError):
        await execute_scenario(
            cast(AsyncSession, FakeSession(existing=original)),
            scene=world,
            perception=perception(world),
            command=changed,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
