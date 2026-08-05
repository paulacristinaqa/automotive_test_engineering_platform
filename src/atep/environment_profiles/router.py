from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.environment_profiles.models import EnvironmentProfile
from atep.environment_profiles.schemas import (
    PROFILE_ID_PATTERN,
    EnvironmentProfileCreate,
    EnvironmentProfilePage,
    EnvironmentProfileResponse,
    EnvironmentProfileStatus,
    EnvironmentProfileStatusUpdate,
)
from atep.environment_profiles.service import (
    create_environment_profile,
    list_environment_profiles,
    require_environment_profile,
    update_environment_profile_status,
)
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id

router = APIRouter(prefix="/environment-profiles", tags=["environment-profiles"])
profiles_read = require_permissions(PermissionName.ENVIRONMENT_PROFILES_READ.value)
profiles_manage = require_permissions(PermissionName.ENVIRONMENT_PROFILES_MANAGE.value)


def profile_response(profile: EnvironmentProfile) -> EnvironmentProfileResponse:
    return EnvironmentProfileResponse(
        id=profile.id,
        profile_id=profile.profile_id,
        created_by_user_id=profile.created_by_user_id,
        name=profile.name,
        description=profile.description,
        vehicle_kind=profile.vehicle_kind,
        property_source=profile.property_source,
        configuration=profile.configuration,
        status=profile.status,
        version=profile.version,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.post("", response_model=EnvironmentProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_environment_profile_endpoint(
    command: EnvironmentProfileCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(profiles_manage)],
) -> EnvironmentProfileResponse:
    profile, duplicate = await create_environment_profile(
        session,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return profile_response(profile)


@router.get("", response_model=EnvironmentProfilePage)
async def list_environment_profiles_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(profiles_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[EnvironmentProfileStatus | None, Query(alias="status")] = None,
) -> EnvironmentProfilePage:
    profiles, total = await list_environment_profiles(
        session, limit=limit, offset=offset, status=status_filter
    )
    return EnvironmentProfilePage(
        items=[profile_response(item) for item in profiles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{profile_id}", response_model=EnvironmentProfileResponse)
async def get_environment_profile_endpoint(
    profile_id: Annotated[str, Path(pattern=PROFILE_ID_PATTERN.pattern)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(profiles_read)],
) -> EnvironmentProfileResponse:
    return profile_response(await require_environment_profile(session, profile_id))


@router.patch("/{profile_id}/status", response_model=EnvironmentProfileResponse)
async def update_environment_profile_status_endpoint(
    profile_id: Annotated[str, Path(pattern=PROFILE_ID_PATTERN.pattern)],
    command: EnvironmentProfileStatusUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(profiles_manage)],
) -> EnvironmentProfileResponse:
    profile = await require_environment_profile(session, profile_id, for_update=True)
    updated, _ = await update_environment_profile_status(
        session,
        profile=profile,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return profile_response(updated)
