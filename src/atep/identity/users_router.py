from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.schemas import UserCreate, UserPage, UserResponse, UserStatusUpdate
from atep.identity.service import (
    assign_role,
    create_user,
    list_users,
    remove_role,
    require_user,
    set_user_status,
)

router = APIRouter(prefix="/users", tags=["users"])


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        roles=sorted(role.name for role in user.roles),
        permissions=sorted(user.permission_names),
    )


def request_correlation_id(request: Request) -> UUID | None:
    value = getattr(request.state, "correlation_id", None)
    return value if isinstance(value, UUID) else None


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(
    command: UserCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permissions(PermissionName.USERS_WRITE.value))],
) -> UserResponse:
    user = await create_user(
        session,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return user_response(user)


@router.get("", response_model=UserPage)
async def list_users_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(require_permissions(PermissionName.USERS_READ.value))],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> UserPage:
    users, total = await list_users(session, limit=limit, offset=offset)
    return UserPage(
        items=[user_response(user) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_endpoint(
    user_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(require_permissions(PermissionName.USERS_READ.value))],
) -> UserResponse:
    return user_response(await require_user(session, user_id))


@router.patch("/{user_id}/status", response_model=UserResponse)
async def update_user_status_endpoint(
    user_id: UUID,
    command: UserStatusUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permissions(PermissionName.USERS_WRITE.value))],
) -> UserResponse:
    user = await set_user_status(
        session,
        user_id=user_id,
        is_active=command.is_active,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return user_response(user)


@router.put("/{user_id}/roles/{role_id}", response_model=UserResponse)
async def assign_role_endpoint(
    user_id: UUID,
    role_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permissions(PermissionName.ROLES_MANAGE.value))],
) -> UserResponse:
    user = await assign_role(
        session,
        user_id=user_id,
        role_id=role_id,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return user_response(user)


@router.delete("/{user_id}/roles/{role_id}", response_model=UserResponse)
async def remove_role_endpoint(
    user_id: UUID,
    role_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_permissions(PermissionName.ROLES_MANAGE.value))],
) -> UserResponse:
    user = await remove_role(
        session,
        user_id=user_id,
        role_id=role_id,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return user_response(user)
