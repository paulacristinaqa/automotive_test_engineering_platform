from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.models import AdasPerceptionResult, AdasWorldScene
from atep.adas.planning_service import create_planning_evaluation, evaluate_plan
from atep.adas.schemas import PerceptionPrediction, PlanningEvaluationCreate
from atep.audit.models import AuditRecord
from atep.core.errors import AdasSceneContractError, AdasSceneVersionConflictError
from atep.events.models import OutboxEvent


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    @asynccontextmanager
    async def begin_nested(self) -> AsyncIterator[None]:
        yield


def world_scene(
    *, ego_y: float = 0, ego_speed: float = 10, lead_distance: float = 40, lead_speed: float = 10
) -> AdasWorldScene:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    common = {
        "heading_deg": 0,
        "length_m": 4.5,
        "width_m": 1.8,
        "height_m": 1.5,
        "trajectory": [],
    }
    return AdasWorldScene(
        id=uuid4(),
        vehicle_id=uuid4(),
        scene_id="planning-scene-001",
        name="Planning scene",
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
                "position_m": {"x": 0, "y": ego_y, "z": 0},
                "velocity_mps": {"x": ego_speed, "y": 0, "z": 0},
                **common,
            },
            {
                "actor_id": "lead",
                "actor_type": "vehicle",
                "position_m": {"x": lead_distance, "y": 0, "z": 0},
                "velocity_mps": {"x": lead_speed, "y": 0, "z": 0},
                **common,
            },
        ],
        environment={},
        traffic_controls=[],
        revision=5,
        simulation_time_ms=3_000,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def command() -> PlanningEvaluationCreate:
    return PlanningEvaluationCreate(
        evaluation_id="evaluation-001",
        expected_scene_revision=5,
        ego_lane_id="lane-1",
        minimum_following_distance_m=15,
        collision_warning_ttc_s=4,
        emergency_brake_ttc_s=1.5,
        lane_departure_margin_m=0.2,
    )


def actor_prediction() -> PerceptionPrediction:
    return PerceptionPrediction(
        prediction_id="prediction-1",
        target_type="object",
        ground_truth_id="lead",
        classification="vehicle",
        confidence=0.98,
    )


def perception(predictions: list[PerceptionPrediction]) -> AdasPerceptionResult:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    return AdasPerceptionResult(
        id=uuid4(),
        sensor_observation_id=uuid4(),
        result_id="result-001",
        scene_revision=5,
        model_name="reference",
        model_version="1.0",
        predictions=[item.model_dump(mode="json") for item in predictions],
        overall_score={},
        scores_by_target={},
        requested_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def test_planning_ttc_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="lower than"):
        PlanningEvaluationCreate.model_validate(
            {**command().model_dump(mode="json"), "emergency_brake_ttc_s": 4}
        )


def test_safe_plan_maintains_lane_without_alerts() -> None:
    metrics, maneuver, alerts = evaluate_plan(
        scene=world_scene(), predictions=[actor_prediction()], command=command()
    )
    assert maneuver == "maintain_lane"
    assert metrics.safe_following_distance is True
    assert metrics.minimum_ttc_s is None
    assert alerts == []


def test_imminent_collision_requests_emergency_brake() -> None:
    metrics, maneuver, alerts = evaluate_plan(
        scene=world_scene(ego_speed=20, lead_distance=10, lead_speed=0),
        predictions=[actor_prediction()],
        command=command(),
    )
    assert metrics.minimum_ttc_s == 0.5
    assert maneuver == "emergency_brake"
    assert [item.alert_type for item in alerts] == [
        "forward_collision",
        "unsafe_following_distance",
    ]
    assert alerts[0].severity == "critical"


def test_lane_departure_requests_lane_centering() -> None:
    metrics, maneuver, alerts = evaluate_plan(
        scene=world_scene(ego_y=1.0), predictions=[], command=command()
    )
    assert metrics.lane_departure is True
    assert maneuver == "lane_centering"
    assert alerts[0].alert_type == "lane_departure"


def test_red_signal_requests_stop() -> None:
    red = PerceptionPrediction(
        prediction_id="signal-prediction",
        target_type="signal",
        ground_truth_id="signal-1",
        classification="red",
        confidence=0.9,
    )
    metrics, maneuver, alerts = evaluate_plan(
        scene=world_scene(), predictions=[red], command=command()
    )
    assert metrics.red_signal_detected is True
    assert maneuver == "stop"
    assert alerts[0].alert_type == "red_signal"


def test_emergency_brake_has_priority_over_red_signal_stop() -> None:
    red = PerceptionPrediction(
        prediction_id="signal-prediction",
        target_type="signal",
        ground_truth_id="signal-1",
        classification="red",
        confidence=0.9,
    )
    _, maneuver, alerts = evaluate_plan(
        scene=world_scene(ego_speed=20, lead_distance=10, lead_speed=0),
        predictions=[actor_prediction(), red],
        command=command(),
    )
    assert maneuver == "emergency_brake"
    assert [item.alert_type for item in alerts] == [
        "forward_collision",
        "unsafe_following_distance",
        "red_signal",
    ]


def test_unknown_ego_lane_is_rejected() -> None:
    invalid = PlanningEvaluationCreate.model_validate(
        {**command().model_dump(mode="json"), "ego_lane_id": "unknown-lane"}
    )
    with pytest.raises(AdasSceneContractError, match="does not exist"):
        evaluate_plan(scene=world_scene(), predictions=[], command=invalid)


@pytest.mark.asyncio
async def test_planning_evaluation_persists_atomic_minimized_evidence() -> None:
    fake = FakeSession()
    result = await create_planning_evaluation(
        cast(AsyncSession, fake),
        scene=world_scene(),
        perception=perception([actor_prediction()]),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert result.maneuver == "maintain_lane"
    events = [item for item in fake.added if isinstance(item, OutboxEvent)]
    audits = [item for item in fake.added if isinstance(item, AuditRecord)]
    assert events[0].event_type == "atep.adas.planning.evaluation.created.v1"
    assert "alerts" not in events[0].payload
    assert audits[0].action == "adas.planning_evaluation_created"


@pytest.mark.asyncio
async def test_planning_rejects_changed_scene_revision_before_writes() -> None:
    scene = world_scene()
    scene.revision = 6
    fake = FakeSession()
    with pytest.raises(AdasSceneVersionConflictError):
        await create_planning_evaluation(
            cast(AsyncSession, fake),
            scene=scene,
            perception=perception([]),
            command=command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert fake.added == []
