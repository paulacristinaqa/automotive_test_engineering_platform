from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.models import AdasWorldScene
from atep.adas.schemas import WorldActor, WorldSceneAdvance, WorldSceneCreate, WorldSceneResponse
from atep.audit.service import record_audit
from atep.core.errors import (
    AdasSceneConflictError,
    AdasSceneVersionConflictError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


def scene_response(scene: AdasWorldScene, vehicle: Vehicle) -> WorldSceneResponse:
    return WorldSceneResponse(
        id=scene.id,
        vehicle_id=vehicle.identifier,
        scene_id=scene.scene_id,
        name=scene.name,
        coordinate_frame=scene.coordinate_frame,
        roads=scene.roads,
        actors=scene.actors,
        revision=scene.revision,
        simulation_time_ms=scene.simulation_time_ms,
        created_by_user_id=scene.created_by_user_id,
        created_at=scene.created_at,
        updated_at=scene.updated_at,
    )


async def create_scene(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: WorldSceneCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> AdasWorldScene:
    scene = AdasWorldScene(
        vehicle_id=vehicle.id,
        scene_id=command.scene_id,
        name=command.name,
        coordinate_frame=command.coordinate_frame.model_dump(mode="json"),
        roads=[item.model_dump(mode="json") for item in command.roads],
        actors=[item.model_dump(mode="json") for item in command.actors],
        revision=1,
        simulation_time_ms=0,
        created_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(scene)
            await session.flush()
    except IntegrityError as exc:
        raise AdasSceneConflictError() from exc
    evidence = {
        "vehicle_id": vehicle.identifier,
        "scene_id": scene.scene_id,
        "revision": scene.revision,
        "road_count": len(scene.roads),
        "actor_count": len(scene.actors),
        "coordinate_convention": "ENU",
    }
    enqueue_event(
        session,
        event_type="atep.adas.world_scene.created.v1",
        aggregate_type="adas_world_scene",
        aggregate_id=scene.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="adas.world_scene_created",
        resource_type="adas_world_scene",
        resource_id=scene.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return scene


async def list_scenes(
    session: AsyncSession, *, vehicle_id: UUID, limit: int, offset: int
) -> tuple[list[AdasWorldScene], int]:
    base = select(AdasWorldScene).where(AdasWorldScene.vehicle_id == vehicle_id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    result = await session.execute(
        base.order_by(AdasWorldScene.created_at.desc(), AdasWorldScene.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def require_scene(
    session: AsyncSession, *, vehicle_id: UUID, scene_id: str
) -> AdasWorldScene:
    scene = await session.scalar(
        select(AdasWorldScene).where(
            AdasWorldScene.vehicle_id == vehicle_id, AdasWorldScene.scene_id == scene_id
        )
    )
    if scene is None:
        raise ResourceNotFoundError("adas_world_scene")
    return scene


async def advance_scene(
    session: AsyncSession,
    *,
    scene: AdasWorldScene,
    command: WorldSceneAdvance,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> AdasWorldScene:
    if scene.revision != command.expected_revision:
        raise AdasSceneVersionConflictError(
            expected=command.expected_revision, actual=scene.revision
        )
    seconds = command.duration_ms / 1000
    advanced: list[dict[str, object]] = []
    for raw in scene.actors:
        actor = WorldActor.model_validate(raw)
        actor.position_m.x = round(actor.position_m.x + actor.velocity_mps.x * seconds, 6)
        actor.position_m.y = round(actor.position_m.y + actor.velocity_mps.y * seconds, 6)
        actor.position_m.z = round(actor.position_m.z + actor.velocity_mps.z * seconds, 6)
        advanced.append(actor.model_dump(mode="json"))
    previous_revision = scene.revision
    scene.actors = advanced
    scene.revision += 1
    scene.simulation_time_ms += command.duration_ms
    await session.flush()
    evidence = {
        "scene_id": scene.scene_id,
        "previous_revision": previous_revision,
        "revision": scene.revision,
        "duration_ms": command.duration_ms,
        "simulation_time_ms": scene.simulation_time_ms,
    }
    enqueue_event(
        session,
        event_type="atep.adas.world_scene.advanced.v1",
        aggregate_type="adas_world_scene",
        aggregate_id=scene.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="adas.world_scene_advanced",
        resource_type="adas_world_scene",
        resource_id=scene.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return scene
