from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.schemas import (
    WorldSceneAdvance,
    WorldSceneContextUpdate,
    WorldSceneCreate,
    WorldScenePage,
    WorldSceneResponse,
)
from atep.adas.service import (
    advance_scene,
    create_scene,
    list_scenes,
    require_scene,
    scene_response,
    update_scene_context,
)
from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.vehicles.service import require_vehicle

router = APIRouter(prefix="/vehicles/{vehicle_id}/adas/scenes", tags=["adas"])
adas_read = require_permissions(PermissionName.ADAS_READ.value)
adas_manage = require_permissions(PermissionName.ADAS_MANAGE.value)


@router.post("", response_model=WorldSceneResponse, status_code=status.HTTP_201_CREATED)
async def create_scene_endpoint(
    vehicle_id: str,
    command: WorldSceneCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> WorldSceneResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await create_scene(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(scene, attribute_names=["created_at", "updated_at"])
    return scene_response(scene, vehicle)


@router.get("", response_model=WorldScenePage)
async def list_scenes_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(adas_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> WorldScenePage:
    vehicle = await require_vehicle(session, vehicle_id)
    scenes, total = await list_scenes(session, vehicle_id=vehicle.id, limit=limit, offset=offset)
    return WorldScenePage(
        items=[scene_response(item, vehicle) for item in scenes],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{scene_id}", response_model=WorldSceneResponse)
async def get_scene_endpoint(
    vehicle_id: str,
    scene_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(adas_read)],
) -> WorldSceneResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    return scene_response(
        await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id), vehicle
    )


@router.post("/{scene_id}/advance", response_model=WorldSceneResponse)
async def advance_scene_endpoint(
    vehicle_id: str,
    scene_id: str,
    command: WorldSceneAdvance,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> WorldSceneResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    await advance_scene(
        session,
        scene=scene,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(scene, attribute_names=["updated_at"])
    return scene_response(scene, vehicle)


@router.patch("/{scene_id}/context", response_model=WorldSceneResponse)
async def update_scene_context_endpoint(
    vehicle_id: str,
    scene_id: str,
    command: WorldSceneContextUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> WorldSceneResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    await update_scene_context(
        session,
        scene=scene,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(scene, attribute_names=["updated_at"])
    return scene_response(scene, vehicle)
