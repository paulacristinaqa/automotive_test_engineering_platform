from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    DuplicateRoleNameError,
    ProtectedRoleError,
    ResourceNotFoundError,
    RoleInUseError,
)
from atep.identity.models import Permission, Role, role_permissions, user_roles
from atep.identity.roles_schemas import RoleCreate, RoleUpdate

PROTECTED_ROLE_NAME = "platform-admin"


async def list_roles(session: AsyncSession, *, limit: int, offset: int) -> tuple[list[Role], int]:
    total = await session.scalar(select(func.count()).select_from(Role))
    result = await session.execute(
        select(Role).order_by(Role.name, Role.id).limit(limit).offset(offset)
    )
    return list(result.scalars().unique().all()), int(total or 0)


async def list_permissions(session: AsyncSession) -> list[Permission]:
    result = await session.execute(select(Permission).order_by(Permission.name))
    return list(result.scalars().all())


async def require_role(session: AsyncSession, role_id: UUID) -> Role:
    role = await session.get(Role, role_id)
    if role is None:
        raise ResourceNotFoundError("role")
    return role


async def require_permission(session: AsyncSession, name: str) -> Permission:
    permission = await session.scalar(
        select(Permission).where(Permission.name == name.strip().casefold())
    )
    if permission is None:
        raise ResourceNotFoundError("permission")
    return permission


async def _resolve_permissions(session: AsyncSession, names: list[str]) -> list[Permission]:
    if not names:
        return []
    result = await session.execute(select(Permission).where(Permission.name.in_(names)))
    permissions = list(result.scalars().all())
    if {item.name for item in permissions} != set(names):
        raise ResourceNotFoundError("permission")
    return permissions


async def create_role(
    session: AsyncSession,
    *,
    command: RoleCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> Role:
    existing = await session.scalar(select(Role).where(Role.name == command.name))
    if existing is not None:
        raise DuplicateRoleNameError()
    role = Role(
        name=command.name,
        description=command.description,
        permissions=await _resolve_permissions(session, command.permissions),
    )
    try:
        async with session.begin_nested():
            session.add(role)
            await session.flush()
    except IntegrityError as exc:
        raise DuplicateRoleNameError() from exc
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="identity.role.created",
        resource_type="role",
        resource_id=role.id,
        correlation_id=correlation_id,
        details={
            "name": role.name,
            "permissions": sorted(item.name for item in role.permissions),
        },
    )
    return role


async def update_role(
    session: AsyncSession,
    *,
    role_id: UUID,
    command: RoleUpdate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> Role:
    role = await require_role(session, role_id)
    if role.name == PROTECTED_ROLE_NAME and command.name not in (None, role.name):
        raise ProtectedRoleError()
    previous = {"name": role.name, "description": role.description}
    if command.name is not None:
        duplicate = await session.scalar(
            select(Role).where(Role.name == command.name, Role.id != role.id)
        )
        if duplicate is not None:
            raise DuplicateRoleNameError()
        role.name = command.name
    if command.description is not None:
        role.description = command.description
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        raise DuplicateRoleNameError() from exc
    await session.refresh(role, attribute_names=["updated_at"])
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="identity.role.updated",
        resource_type="role",
        resource_id=role.id,
        correlation_id=correlation_id,
        details={
            "previous": previous,
            "current": {"name": role.name, "description": role.description},
        },
    )
    return role


async def grant_permission(
    session: AsyncSession,
    *,
    role_id: UUID,
    permission_name: str,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> Role:
    role = await require_role(session, role_id)
    permission = await require_permission(session, permission_name)
    if all(item.id != permission.id for item in role.permissions):
        role.permissions.append(permission)
        record_audit(
            session,
            actor_user_id=actor_user_id,
            action="identity.role.permission_granted",
            resource_type="role",
            resource_id=role.id,
            correlation_id=correlation_id,
            details={"permission": permission.name},
        )
    return role


async def revoke_permission(
    session: AsyncSession,
    *,
    role_id: UUID,
    permission_name: str,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> Role:
    role = await require_role(session, role_id)
    if role.name == PROTECTED_ROLE_NAME:
        raise ProtectedRoleError()
    normalized_name = permission_name.strip().casefold()
    permission = next((item for item in role.permissions if item.name == normalized_name), None)
    if permission is None:
        raise ResourceNotFoundError("permission_assignment")
    role.permissions.remove(permission)
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="identity.role.permission_revoked",
        resource_type="role",
        resource_id=role.id,
        correlation_id=correlation_id,
        details={"permission": permission.name},
    )
    return role


async def delete_role(
    session: AsyncSession,
    *,
    role_id: UUID,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> None:
    role = await require_role(session, role_id)
    if role.name == PROTECTED_ROLE_NAME:
        raise ProtectedRoleError()
    assignments = await session.scalar(
        select(func.count()).select_from(user_roles).where(user_roles.c.role_id == role.id)
    )
    if assignments:
        raise RoleInUseError()
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="identity.role.deleted",
        resource_type="role",
        resource_id=role.id,
        correlation_id=correlation_id,
        details={"name": role.name},
    )
    await session.execute(role_permissions.delete().where(role_permissions.c.role_id == role.id))
    await session.delete(role)
