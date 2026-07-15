from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import Permission, Role, User
from atep.identity.permissions import PermissionName
from atep.identity.roles_schemas import (
    PermissionResponse,
    RoleCreate,
    RolePage,
    RoleResponse,
    RoleUpdate,
)
from atep.identity.roles_service import (
    create_role,
    delete_role,
    grant_permission,
    list_permissions,
    list_roles,
    require_role,
    revoke_permission,
    update_role,
)
from atep.identity.users_router import request_correlation_id

router = APIRouter(tags=["roles"])


def role_response(role: Role) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=sorted(item.name for item in role.permissions),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


def permission_response(permission: Permission) -> PermissionResponse:
    return PermissionResponse(
        id=permission.id,
        name=permission.name,
        description=permission.description,
    )


roles_manage = require_permissions(PermissionName.ROLES_MANAGE.value)


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(roles_manage)],
) -> list[PermissionResponse]:
    return [permission_response(item) for item in await list_permissions(session)]


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role_endpoint(
    command: RoleCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(roles_manage)],
) -> RoleResponse:
    role = await create_role(
        session,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return role_response(role)


@router.get("/roles", response_model=RolePage)
async def list_roles_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(roles_manage)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> RolePage:
    roles, total = await list_roles(session, limit=limit, offset=offset)
    return RolePage(
        items=[role_response(role) for role in roles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/roles/{role_id}", response_model=RoleResponse)
async def get_role_endpoint(
    role_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(roles_manage)],
) -> RoleResponse:
    return role_response(await require_role(session, role_id))


@router.patch("/roles/{role_id}", response_model=RoleResponse)
async def update_role_endpoint(
    role_id: UUID,
    command: RoleUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(roles_manage)],
) -> RoleResponse:
    role = await update_role(
        session,
        role_id=role_id,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return role_response(role)


@router.put("/roles/{role_id}/permissions/{permission_name}", response_model=RoleResponse)
async def grant_permission_endpoint(
    role_id: UUID,
    permission_name: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(roles_manage)],
) -> RoleResponse:
    role = await grant_permission(
        session,
        role_id=role_id,
        permission_name=permission_name,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return role_response(role)


@router.delete("/roles/{role_id}/permissions/{permission_name}", response_model=RoleResponse)
async def revoke_permission_endpoint(
    role_id: UUID,
    permission_name: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(roles_manage)],
) -> RoleResponse:
    role = await revoke_permission(
        session,
        role_id=role_id,
        permission_name=permission_name,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return role_response(role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role_endpoint(
    role_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(roles_manage)],
) -> Response:
    await delete_role(
        session,
        role_id=role_id,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
