from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.models import AdasSensorObservation, AdasWorldScene
from atep.adas.perception_service import (
    build_ground_truth,
    create_perception_result,
    score_predictions,
)
from atep.adas.schemas import PerceptionPrediction, PerceptionResultCreate
from atep.audit.models import AuditRecord
from atep.core.errors import AdasSceneVersionConflictError
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


def scene_and_observation() -> tuple[AdasWorldScene, AdasSensorObservation]:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    actor_defaults = {
        "velocity_mps": {"x": 0, "y": 0, "z": 0},
        "heading_deg": 0,
        "length_m": 4.5,
        "width_m": 1.8,
        "height_m": 1.5,
        "trajectory": [],
    }
    scene = AdasWorldScene(
        id=uuid4(),
        vehicle_id=uuid4(),
        scene_id="perception-scene-001",
        name="Perception scene",
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
                **actor_defaults,
            },
            {
                "actor_id": "vehicle-1",
                "actor_type": "vehicle",
                "position_m": {"x": 10, "y": 0, "z": 0},
                **actor_defaults,
            },
            {
                "actor_id": "pedestrian-1",
                "actor_type": "pedestrian",
                "position_m": {"x": 15, "y": 2, "z": 0},
                **actor_defaults,
            },
        ],
        environment={
            "weather": "clear",
            "precipitation_mm_per_h": 0,
            "visibility_m": 10_000,
            "ambient_light_lux": 10_000,
            "road_friction_coefficient": 0.9,
            "temperature_c": 20,
            "wind_speed_mps": 0,
        },
        traffic_controls=[
            {
                "control_id": "signal-1",
                "control_type": "traffic_light",
                "position_m": {"x": 20, "y": 0, "z": 3},
                "lane_ids": ["lane-1"],
                "light_state": "red",
            },
            {
                "control_id": "sign-1",
                "control_type": "stop_sign",
                "position_m": {"x": 18, "y": 1, "z": 2},
                "lane_ids": ["lane-1"],
            },
        ],
        revision=4,
        simulation_time_ms=2_000,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    observation = AdasSensorObservation(
        id=uuid4(),
        sensor_configuration_id=uuid4(),
        observation_id="observation-001",
        scene_revision=4,
        scene_simulation_time_ms=2_000,
        observed_simulation_time_ms=1_900,
        seed=8,
        detections=[{"actor_id": "vehicle-1"}, {"actor_id": "pedestrian-1"}],
        metrics={},
        requested_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    return scene, observation


def perfect_predictions() -> list[PerceptionPrediction]:
    values = [
        ("p1", "object", "vehicle-1", "vehicle"),
        ("p2", "pedestrian", "pedestrian-1", "pedestrian"),
        ("p3", "lane", "lane-1", "lane"),
        ("p4", "signal", "signal-1", "red"),
        ("p5", "sign", "sign-1", "stop_sign"),
    ]
    return [
        PerceptionPrediction(
            prediction_id=item[0],
            target_type=item[1],
            ground_truth_id=item[2],
            classification=item[3],
            confidence=0.95,
        )
        for item in values
    ]


def test_prediction_identifiers_must_be_unique() -> None:
    prediction = perfect_predictions()[0]
    with pytest.raises(ValidationError):
        PerceptionResultCreate(
            result_id="result-001",
            model_name="perception",
            model_version="1.0",
            predictions=[prediction, prediction],
        )


def test_perfect_perception_scores_all_ground_truth_types() -> None:
    scene, observation = scene_and_observation()
    ground_truth = build_ground_truth(scene=scene, observation=observation)
    overall, by_target = score_predictions(
        predictions=perfect_predictions(), ground_truth=ground_truth
    )
    assert len(ground_truth) == 5
    assert overall.model_dump() == {
        "true_positive": 5,
        "false_positive": 0,
        "false_negative": 0,
        "precision": 1.0,
        "recall": 1.0,
        "f1_score": 1.0,
    }
    assert all(score.f1_score == 1 for score in by_target.values())


def test_duplicate_and_misclassified_predictions_are_not_double_counted() -> None:
    scene, observation = scene_and_observation()
    predictions = perfect_predictions()
    predictions.append(predictions[0].model_copy(update={"prediction_id": "duplicate"}))
    predictions[1] = predictions[1].model_copy(update={"classification": "cyclist"})
    overall, _ = score_predictions(
        predictions=predictions,
        ground_truth=build_ground_truth(scene=scene, observation=observation),
    )
    assert (overall.true_positive, overall.false_positive, overall.false_negative) == (4, 2, 1)


@pytest.mark.asyncio
async def test_perception_result_persists_scores_and_atomic_evidence() -> None:
    scene, observation = scene_and_observation()
    fake = FakeSession()
    result = await create_perception_result(
        cast(AsyncSession, fake),
        scene=scene,
        observation=observation,
        command=PerceptionResultCreate(
            result_id="result-001",
            model_name="reference-perception",
            model_version="1.0.0",
            predictions=perfect_predictions(),
        ),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert result.overall_score["f1_score"] == 1
    events = [item for item in fake.added if isinstance(item, OutboxEvent)]
    audits = [item for item in fake.added if isinstance(item, AuditRecord)]
    assert events[0].event_type == "atep.adas.perception.result.created.v1"
    assert "predictions" not in events[0].payload
    assert audits[0].action == "adas.perception_result_created"


@pytest.mark.asyncio
async def test_perception_scoring_rejects_changed_scene_truth() -> None:
    scene, observation = scene_and_observation()
    scene.revision += 1
    fake = FakeSession()
    with pytest.raises(AdasSceneVersionConflictError):
        await create_perception_result(
            cast(AsyncSession, fake),
            scene=scene,
            observation=observation,
            command=PerceptionResultCreate(
                result_id="result-002",
                model_name="reference-perception",
                model_version="1.0.0",
                predictions=[],
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert fake.added == []
