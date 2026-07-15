from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.errors import ProtectedRoleError
from atep.identity.models import Role
from atep.identity.roles_schemas import RoleCreate, RoleUpdate
from atep.identity.roles_service import delete_role, revoke_permission, update_role


class ProtectedRoleSession:
    def __init__(self) -> None:
        self.role = Role(
            id=uuid4(),
            name="platform-admin",
            description="Full platform administration",
            permissions=[],
        )

    async def get(self, _: type[Any], __: object) -> Role:
        return self.role


def test_role_commands_normalize_names_descriptions_and_permissions() -> None:
    command = RoleCreate(
        name="  QA-Lead ",
        description="  Quality lead  ",
        permissions=["users:read", " USERS:READ ", "users:write"],
    )
    assert command.name == "qa-lead"
    assert command.description == "Quality lead"
    assert command.permissions == ["users:read", "users:write"]


@pytest.mark.parametrize("name", ["admin role", "-admin", "a", "admin_role"])
def test_role_name_rejects_unsafe_catalogue_identifiers(name: str) -> None:
    with pytest.raises(ValidationError):
        RoleCreate(name=name)


def test_empty_role_update_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RoleUpdate()


@pytest.mark.asyncio
async def test_platform_admin_cannot_be_renamed() -> None:
    session = ProtectedRoleSession()
    with pytest.raises(ProtectedRoleError) as captured:
        await update_role(
            cast(AsyncSession, session),
            role_id=session.role.id,
            command=RoleUpdate(name="replacement-admin"),
            actor_user_id=uuid4(),
            correlation_id=uuid4(),
        )
    assert captured.value.code == "protected_role"


@pytest.mark.asyncio
async def test_platform_admin_permissions_and_existence_are_protected() -> None:
    session = ProtectedRoleSession()
    with pytest.raises(ProtectedRoleError):
        await revoke_permission(
            cast(AsyncSession, session),
            role_id=session.role.id,
            permission_name="users:read",
            actor_user_id=uuid4(),
            correlation_id=uuid4(),
        )
    with pytest.raises(ProtectedRoleError):
        await delete_role(
            cast(AsyncSession, session),
            role_id=session.role.id,
            actor_user_id=uuid4(),
            correlation_id=uuid4(),
        )
