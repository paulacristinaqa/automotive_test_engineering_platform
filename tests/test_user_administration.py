from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import DuplicateEmailError
from atep.events.models import OutboxEvent
from atep.identity.dependencies import require_permissions
from atep.identity.models import Permission, Role, User
from atep.identity.permissions import PermissionName
from atep.identity.schemas import UserCreate
from atep.identity.service import assign_role, create_user, remove_role, set_user_status
from atep.identity.users_router import user_response


class ScalarResult:
    def __init__(self, value: User | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> User | None:
        return self.value


class NestedTransaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class CreateSession:
    def __init__(self, existing: User | None = None) -> None:
        self.existing = existing
        self.added: list[Any] = []

    async def execute(self, _: Any) -> ScalarResult:
        return ScalarResult(self.existing)

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if isinstance(value, User) and value.id is None:
                value.id = uuid4()


def user_with_permissions(*names: str, active: bool = True) -> User:
    permissions = [Permission(id=uuid4(), name=name, description="") for name in names]
    role = Role(id=uuid4(), name="test-role", description="", permissions=permissions)
    return User(
        id=uuid4(),
        email="actor@example.com",
        display_name="Actor",
        password_hash="not-returned",
        is_active=active,
        roles=[role],
    )


@pytest.mark.asyncio
async def test_create_user_records_event_and_audit_without_exposing_password() -> None:
    session = CreateSession()
    actor_id = uuid4()
    correlation_id = uuid4()
    user = await create_user(
        cast(AsyncSession, session),
        command=UserCreate(
            email="  New.Engineer@Example.com ",
            display_name="New Engineer",
            password=SecretStr("correct horse battery staple"),
        ),
        actor_user_id=actor_id,
        correlation_id=correlation_id,
    )

    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    response = user_response(user).model_dump()

    assert user.email == "new.engineer@example.com"
    assert user.roles == []
    assert user.password_hash != "correct horse battery staple"
    assert "password" not in response and "password_hash" not in response
    assert len(events) == 1
    assert events[0].event_type == "atep.identity.user.created.v1"
    assert "password" not in events[0].payload
    assert len(audits) == 1
    assert audits[0].actor_user_id == actor_id
    assert audits[0].correlation_id == correlation_id


@pytest.mark.asyncio
async def test_duplicate_email_returns_stable_domain_error() -> None:
    existing = user_with_permissions()
    existing.email = "duplicate@example.com"
    session = CreateSession(existing)

    with pytest.raises(DuplicateEmailError) as captured:
        await create_user(
            cast(AsyncSession, session),
            command=UserCreate(
                email="Duplicate@Example.com",
                display_name="Duplicate",
                password=SecretStr("correct horse battery staple"),
            ),
            actor_user_id=uuid4(),
            correlation_id=uuid4(),
        )

    assert captured.value.code == "email_already_exists"
    assert captured.value.status_code == 409
    assert not session.added


@pytest.mark.asyncio
async def test_permission_dependency_denies_user_without_required_permission() -> None:
    dependency = require_permissions(PermissionName.USERS_WRITE.value)
    with pytest.raises(HTTPException) as captured:
        await dependency(user_with_permissions(PermissionName.USERS_READ.value))
    assert captured.value.status_code == 403
    assert isinstance(captured.value.detail, dict)
    assert captured.value.detail["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_permission_dependency_accepts_exact_permission() -> None:
    user = user_with_permissions(PermissionName.ROLES_MANAGE.value)
    dependency = require_permissions(PermissionName.ROLES_MANAGE.value)
    assert await dependency(user) is user


class UserSession(CreateSession):
    def __init__(self, user: User) -> None:
        super().__init__()
        self.user = user

    async def get(self, model: type[Any], _: object) -> Any:
        return self.user if model is User else None


@pytest.mark.asyncio
async def test_status_change_is_immediate_and_audited() -> None:
    user = user_with_permissions(PermissionName.USERS_READ.value)
    session = UserSession(user)
    actor_id = uuid4()

    changed = await set_user_status(
        cast(AsyncSession, session),
        user_id=user.id,
        is_active=False,
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )

    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert changed.is_active is False
    assert audits[0].action == "identity.user.status_changed"
    assert audits[0].details == {"previous": True, "current": False}


class RoleSession(UserSession):
    def __init__(self, user: User, role: Role) -> None:
        super().__init__(user)
        self.role = role

    async def get(self, model: type[Any], _: object) -> Any:
        if model is User:
            return self.user
        if model is Role:
            return self.role
        return None


@pytest.mark.asyncio
async def test_role_assignment_and_removal_are_audited() -> None:
    user = user_with_permissions()
    role = Role(id=uuid4(), name="qa-lead", description="", permissions=[])
    session = RoleSession(user, role)
    actor_id = uuid4()

    assigned = await assign_role(
        cast(AsyncSession, session),
        user_id=user.id,
        role_id=role.id,
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )
    assert role in assigned.roles

    removed = await remove_role(
        cast(AsyncSession, session),
        user_id=user.id,
        role_id=role.id,
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )
    assert role not in removed.roles
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "identity.user.role_assigned",
        "identity.user.role_removed",
    ]
