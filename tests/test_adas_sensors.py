from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.models import AdasSensorConfiguration, AdasWorldScene
from atep.adas.schemas import SensorConfigurationCreate, SensorObservationCreate
from atep.adas.sensor_service import capture_observation, simulate_detections
from atep.audit.models import AuditRecord
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


def world_scene() -> AdasWorldScene:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    dimensions = {
        "velocity_mps": {"x": 0, "y": 0, "z": 0},
        "heading_deg": 0,
        "length_m": 4.5,
        "width_m": 1.8,
        "height_m": 1.5,
        "trajectory": [],
    }
    actors = [
        {
            "actor_id": "ego",
            "actor_type": "ego_vehicle",
            "position_m": {"x": 0, "y": 0, "z": 0},
            **dimensions,
        },
        {
            "actor_id": "near",
            "actor_type": "vehicle",
            "position_m": {"x": 10, "y": 0, "z": 0},
            **dimensions,
        },
        {
            "actor_id": "far",
            "actor_type": "pedestrian",
            "position_m": {"x": 20, "y": 0, "z": 0},
            **dimensions,
        },
        {
            "actor_id": "outside",
            "actor_type": "cyclist",
            "position_m": {"x": 0, "y": 20, "z": 0},
            **dimensions,
        },
    ]
    return AdasWorldScene(
        id=uuid4(),
        vehicle_id=uuid4(),
        scene_id="sensor-scene-001",
        name="Sensor scene",
        coordinate_frame={
            "convention": "ENU",
            "origin_latitude_deg": 0,
            "origin_longitude_deg": 0,
            "origin_altitude_m": 0,
        },
        roads=[],
        actors=actors,
        environment={
            "weather": "clear",
            "precipitation_mm_per_h": 0,
            "visibility_m": 10_000,
            "ambient_light_lux": 10_000,
            "road_friction_coefficient": 0.9,
            "temperature_c": 20,
            "wind_speed_mps": 0,
        },
        traffic_controls=[],
        revision=3,
        simulation_time_ms=5_000,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def front_sensor(*, noise: float = 0) -> AdasSensorConfiguration:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    return AdasSensorConfiguration(
        id=uuid4(),
        scene_id=uuid4(),
        sensor_id="front-camera",
        sensor_type="camera",
        mount_position={"x": 0, "y": 0, "z": 1.2},
        yaw_deg=0,
        max_range_m=100,
        horizontal_fov_deg=90,
        latency_ms=120,
        position_noise_stddev_m=noise,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def test_sensor_configuration_has_safe_bounds() -> None:
    with pytest.raises(ValidationError):
        SensorConfigurationCreate(
            sensor_id="front-camera", sensor_type="camera", max_range_m=0, horizontal_fov_deg=361
        )


def test_sensor_filters_fov_and_occlusion() -> None:
    detections, metrics = simulate_detections(scene=world_scene(), sensor=front_sensor(), seed=7)
    assert [item.actor_id for item in detections] == ["near"]
    assert metrics == {
        "candidate_count": 2,
        "detection_count": 1,
        "occluded_count": 1,
        "effective_range_m": 100,
    }


def test_seeded_sensor_noise_is_deterministic() -> None:
    first, _ = simulate_detections(scene=world_scene(), sensor=front_sensor(noise=0.5), seed=42)
    second, _ = simulate_detections(scene=world_scene(), sensor=front_sensor(noise=0.5), seed=42)
    different, _ = simulate_detections(scene=world_scene(), sensor=front_sensor(noise=0.5), seed=43)
    assert first == second
    assert first != different


@pytest.mark.asyncio
async def test_observation_persists_latency_revision_and_atomic_evidence() -> None:
    fake = FakeSession()
    result = await capture_observation(
        cast(AsyncSession, fake),
        scene=world_scene(),
        sensor=front_sensor(),
        command=SensorObservationCreate(
            observation_id="observation-001", expected_scene_revision=3, seed=99
        ),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert result.scene_revision == 3
    assert result.scene_simulation_time_ms == 5_000
    assert result.observed_simulation_time_ms == 4_880
    events = [item for item in fake.added if isinstance(item, OutboxEvent)]
    audits = [item for item in fake.added if isinstance(item, AuditRecord)]
    assert events[0].event_type == "atep.adas.sensor.observation.created.v1"
    assert "detections" not in events[0].payload
    assert audits[0].action == "adas.sensor_observation_created"
