from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.models import AdasWorldScene
from atep.adas.schemas import (
    EnvironmentConditions,
    WorldSceneAdvance,
    WorldSceneContextUpdate,
    WorldSceneCreate,
)
from atep.adas.service import advance_scene, create_scene, update_scene_context
from atep.audit.models import AuditRecord
from atep.core.errors import AdasSceneVersionConflictError
from atep.events.models import OutboxEvent
from atep.vehicles.models import Vehicle


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


def vehicle() -> Vehicle:
    now = datetime(2026, 9, 6, tzinfo=UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="Reference EV",
        model="EV",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def scene_command() -> WorldSceneCreate:
    return WorldSceneCreate.model_validate(
        {
            "scene_id": "urban-crossing-001",
            "name": "Urban crossing",
            "coordinate_frame": {"origin_latitude_deg": 38.72, "origin_longitude_deg": -9.14},
            "roads": [
                {
                    "road_id": "road-1",
                    "lanes": [
                        {"lane_id": "lane-1", "centerline": [{"x": 0, "y": 0}, {"x": 100, "y": 0}]}
                    ],
                }
            ],
            "actors": [
                {
                    "actor_id": "ego",
                    "actor_type": "ego_vehicle",
                    "position_m": {"x": 0, "y": 0},
                    "velocity_mps": {"x": 10, "y": 0},
                    "length_m": 4.5,
                    "width_m": 1.8,
                    "height_m": 1.5,
                },
                {
                    "actor_id": "pedestrian-1",
                    "actor_type": "pedestrian",
                    "position_m": {"x": 20, "y": -4},
                    "velocity_mps": {"x": 0, "y": 1.5},
                    "length_m": 0.5,
                    "width_m": 0.5,
                    "height_m": 1.7,
                },
            ],
        }
    )


def test_world_scene_contract_requires_exactly_one_ego_and_unique_ids() -> None:
    payload = scene_command().model_dump()
    payload["actors"] = [payload["actors"][1]]
    with pytest.raises(ValidationError, match="exactly one ego_vehicle"):
        WorldSceneCreate.model_validate(payload)


@pytest.mark.asyncio
async def test_scene_creation_records_atomic_minimized_evidence() -> None:
    fake = FakeSession()
    item = await create_scene(
        cast(AsyncSession, fake),
        vehicle=vehicle(),
        command=scene_command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert item.revision == 1
    assert item.coordinate_frame["convention"] == "ENU"
    events = [value for value in fake.added if isinstance(value, OutboxEvent)]
    audits = [value for value in fake.added if isinstance(value, AuditRecord)]
    assert events[0].event_type == "atep.adas.world_scene.created.v1"
    assert "actors" not in events[0].payload
    assert audits[0].action == "adas.world_scene_created"


@pytest.mark.asyncio
async def test_scene_advance_is_deterministic_and_uses_logical_time() -> None:
    now = datetime(2026, 9, 6, tzinfo=UTC)
    command = scene_command()
    scene = AdasWorldScene(
        id=uuid4(),
        vehicle_id=uuid4(),
        scene_id=command.scene_id,
        name=command.name,
        coordinate_frame=command.coordinate_frame.model_dump(mode="json"),
        roads=[item.model_dump(mode="json") for item in command.roads],
        actors=[item.model_dump(mode="json") for item in command.actors],
        revision=1,
        simulation_time_ms=0,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    fake = FakeSession()
    await advance_scene(
        cast(AsyncSession, fake),
        scene=scene,
        command=WorldSceneAdvance(duration_ms=2_000, expected_revision=1),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert scene.actors[0]["position_m"] == {"x": 20.0, "y": 0.0, "z": 0.0}
    assert scene.actors[1]["position_m"] == {"x": 20.0, "y": -1.0, "z": 0.0}
    assert scene.revision == 2
    assert scene.simulation_time_ms == 2_000


@pytest.mark.asyncio
async def test_scene_advance_rejects_stale_revision_before_mutation() -> None:
    now = datetime(2026, 9, 6, tzinfo=UTC)
    command = scene_command()
    scene = AdasWorldScene(
        id=uuid4(),
        vehicle_id=uuid4(),
        scene_id=command.scene_id,
        name=command.name,
        coordinate_frame=command.coordinate_frame.model_dump(mode="json"),
        roads=[item.model_dump(mode="json") for item in command.roads],
        actors=[item.model_dump(mode="json") for item in command.actors],
        revision=2,
        simulation_time_ms=0,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(AdasSceneVersionConflictError):
        await advance_scene(
            cast(AsyncSession, FakeSession()),
            scene=scene,
            command=WorldSceneAdvance(duration_ms=1_000, expected_revision=1),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert scene.simulation_time_ms == 0


def test_environment_and_traffic_contracts_reject_inconsistent_ground_truth() -> None:
    with pytest.raises(ValidationError, match="positive precipitation"):
        EnvironmentConditions(weather="rain", precipitation_mm_per_h=0)
    payload = scene_command().model_dump(mode="json")
    payload["traffic_controls"] = [
        {
            "control_id": "light-1",
            "control_type": "traffic_light",
            "position_m": {"x": 20, "y": 0},
            "lane_ids": ["missing-lane"],
            "light_state": "red",
        }
    ]
    with pytest.raises(ValidationError, match="reference lanes in the scene"):
        WorldSceneCreate.model_validate(payload)


@pytest.mark.asyncio
async def test_scene_advance_interpolates_absolute_actor_trajectory() -> None:
    now = datetime(2026, 9, 6, tzinfo=UTC)
    command = scene_command()
    actors = [item.model_dump(mode="json") for item in command.actors]
    actors[1]["trajectory"] = [
        {"time_offset_ms": 0, "position_m": {"x": 20, "y": -4, "z": 0}},
        {"time_offset_ms": 4_000, "position_m": {"x": 20, "y": 2, "z": 0}},
    ]
    scene = AdasWorldScene(
        id=uuid4(),
        vehicle_id=uuid4(),
        scene_id=command.scene_id,
        name=command.name,
        coordinate_frame=command.coordinate_frame.model_dump(mode="json"),
        roads=[item.model_dump(mode="json") for item in command.roads],
        actors=actors,
        environment=command.environment.model_dump(mode="json"),
        traffic_controls=[],
        revision=1,
        simulation_time_ms=0,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    await advance_scene(
        cast(AsyncSession, FakeSession()),
        scene=scene,
        command=WorldSceneAdvance(duration_ms=2_000, expected_revision=1),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert scene.actors[1]["position_m"] == {"x": 20.0, "y": -1.0, "z": 0.0}
    assert scene.actors[1]["velocity_mps"] == {"x": 0.0, "y": 1.5, "z": 0.0}


@pytest.mark.asyncio
async def test_context_update_records_environment_and_traffic_evidence() -> None:
    now = datetime(2026, 9, 6, tzinfo=UTC)
    command = scene_command()
    scene = AdasWorldScene(
        id=uuid4(),
        vehicle_id=uuid4(),
        scene_id=command.scene_id,
        name=command.name,
        coordinate_frame=command.coordinate_frame.model_dump(mode="json"),
        roads=[item.model_dump(mode="json") for item in command.roads],
        actors=[item.model_dump(mode="json") for item in command.actors],
        environment=command.environment.model_dump(mode="json"),
        traffic_controls=[],
        revision=1,
        simulation_time_ms=0,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    fake = FakeSession()
    await update_scene_context(
        cast(AsyncSession, fake),
        scene=scene,
        command=WorldSceneContextUpdate.model_validate(
            {
                "expected_revision": 1,
                "environment": {
                    "weather": "rain",
                    "precipitation_mm_per_h": 12,
                    "visibility_m": 800,
                    "road_friction_coefficient": 0.45,
                },
                "traffic_controls": [
                    {
                        "control_id": "light-1",
                        "control_type": "traffic_light",
                        "position_m": {"x": 30, "y": 0},
                        "lane_ids": ["lane-1"],
                        "light_state": "red",
                    }
                ],
            }
        ),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert scene.environment["weather"] == "rain"
    assert scene.traffic_controls[0]["light_state"] == "red"
    assert scene.revision == 2
    events = [item for item in fake.added if isinstance(item, OutboxEvent)]
    audits = [item for item in fake.added if isinstance(item, AuditRecord)]
    assert events[0].event_type == "atep.adas.world_scene.context_updated.v1"
    assert audits[0].action == "adas.world_scene_context_updated"
    with pytest.raises(AdasSceneVersionConflictError):
        await update_scene_context(
            cast(AsyncSession, FakeSession()),
            scene=scene,
            command=WorldSceneContextUpdate(
                expected_revision=1,
                environment=EnvironmentConditions(),
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert scene.environment["weather"] == "rain"
