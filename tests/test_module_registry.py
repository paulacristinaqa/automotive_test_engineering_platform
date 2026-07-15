from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import InvalidModuleCredentialError
from atep.core.security import verify_module_token
from atep.events.models import OutboxEvent
from atep.identity.dependencies import require_permissions
from atep.identity.models import Permission, Role, User
from atep.identity.permissions import PermissionName
from atep.registry.models import ModuleCapability, PlatformModule
from atep.registry.schemas import (
    CapabilityUpdate,
    ModuleCreate,
    ModuleCredentialCommand,
    ModuleHeartbeat,
    ModuleStatus,
    ModuleUpdate,
)
from atep.registry.service import (
    create_module,
    declare_capability,
    heartbeat_module,
    issue_module_credential,
    reconcile_expired_modules,
    remove_capability,
)


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


class RegistrySession:
    def __init__(self, module: PlatformModule | None = None) -> None:
        self.module = module
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> PlatformModule | None:
        return None

    async def get(self, model: type[Any], _: object) -> Any:
        return self.module if model is PlatformModule else None

    async def execute(self, _: Any) -> "RegistryResult":
        return RegistryResult(self.module)

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        values = list(self.added)
        if self.module is not None:
            values.append(self.module)
        for value in values:
            if getattr(value, "id", None) is None:
                value.id = uuid4()
            for capability in getattr(value, "capabilities", []):
                if capability.id is None:
                    capability.id = uuid4()

    async def refresh(self, _: Any, attribute_names: list[str] | None = None) -> None:
        return None


class RegistryResult:
    def __init__(self, module: PlatformModule | None) -> None:
        self.module = module

    def scalar_one_or_none(self) -> PlatformModule | None:
        return self.module

    def scalars(self) -> "RegistryResult":
        return self

    def all(self) -> list[PlatformModule]:
        return [self.module] if self.module is not None else []


def user_with_permissions(*names: str) -> User:
    permissions = [Permission(id=uuid4(), name=name, description="") for name in names]
    role = Role(id=uuid4(), name="registry-test", description="", permissions=permissions)
    return User(
        id=uuid4(),
        email="registry@example.com",
        display_name="Registry Tester",
        password_hash="not-returned",
        is_active=True,
        roles=[role],
    )


def module_command() -> ModuleCreate:
    return ModuleCreate(
        name="  CAN-Simulator ",
        display_name=" CAN Simulator ",
        description=" Publishes virtual vehicle frames ",
        version="1.2.0",
        base_url="http://can-simulator:8080",
        capabilities=[
            {
                "name": "can.frames.publish",
                "version": "1.0.0",
                "description": "Publish CAN frames",
            }
        ],
    )


def test_module_commands_normalize_names_and_validate_versions() -> None:
    command = module_command()
    assert command.name == "can-simulator"
    assert command.display_name == "CAN Simulator"
    assert command.capabilities[0].name == "can.frames.publish"
    with pytest.raises(ValidationError):
        ModuleCreate(
            name="bad_module",
            display_name="Bad",
            version="latest",
        )


def test_duplicate_capabilities_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ModuleCreate(
            name="can-simulator",
            display_name="CAN Simulator",
            version="1.0.0",
            capabilities=[
                {"name": "can.frames.publish", "version": "1.0.0"},
                {"name": " CAN.FRAMES.PUBLISH ", "version": "1.1.0"},
            ],
        )


def test_operational_status_can_only_be_reported_by_heartbeat() -> None:
    with pytest.raises(ValidationError):
        ModuleUpdate(status=ModuleStatus.ACTIVE)
    with pytest.raises(ValidationError):
        ModuleHeartbeat(status=ModuleStatus.INACTIVE)


@pytest.mark.asyncio
async def test_registration_records_atomic_event_and_audit() -> None:
    session = RegistrySession()
    actor_id = uuid4()
    correlation_id = uuid4()
    module = await create_module(
        cast(AsyncSession, session),
        command=module_command(),
        actor_user_id=actor_id,
        correlation_id=correlation_id,
    )
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert module.name == "can-simulator"
    assert [item.name for item in module.capabilities] == ["can.frames.publish"]
    assert events[0].event_type == "atep.platform.module.registered.v1"
    assert events[0].correlation_id == correlation_id
    assert audits[0].action == "platform.module.registered"
    assert audits[0].actor_user_id == actor_id


@pytest.mark.asyncio
async def test_capability_upsert_and_removal_are_evented_and_audited() -> None:
    module = PlatformModule(
        id=uuid4(),
        name="uds-diagnostics",
        display_name="UDS Diagnostics",
        description="",
        version="1.0.0",
        base_url=None,
        status="registered",
        capabilities=[],
    )
    session = RegistrySession(module)
    actor_id = uuid4()
    await declare_capability(
        cast(AsyncSession, session),
        module_id=module.id,
        capability_name="uds.dtc.read",
        command=CapabilityUpdate(version="1.0.0", description="Read DTCs"),
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )
    assert isinstance(module.capabilities[0], ModuleCapability)
    assert module.capabilities[0].name == "uds.dtc.read"

    await remove_capability(
        cast(AsyncSession, session),
        module_id=module.id,
        capability_name="uds.dtc.read",
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )
    assert module.capabilities == []
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.platform.module.capability-declared.v1",
        "atep.platform.module.capability-removed.v1",
    ]
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "platform.module.capability_declared",
        "platform.module.capability_removed",
    ]


@pytest.mark.asyncio
async def test_registry_permissions_are_independent() -> None:
    reader = user_with_permissions(PermissionName.MODULES_READ.value)
    assert await require_permissions(PermissionName.MODULES_READ.value)(reader) is reader
    with pytest.raises(HTTPException) as captured:
        await require_permissions(PermissionName.MODULES_MANAGE.value)(reader)
    assert captured.value.status_code == 403


@pytest.mark.asyncio
async def test_module_credential_is_hash_only_and_rotation_invalidates_old_token() -> None:
    module = PlatformModule(
        id=uuid4(),
        name="bms",
        display_name="BMS",
        description="",
        version="1.0.0",
        base_url=None,
        status="registered",
        capabilities=[],
    )
    session = RegistrySession(module)
    actor_id = uuid4()
    _, first_token = await issue_module_credential(
        cast(AsyncSession, session),
        module_id=module.id,
        command=ModuleCredentialCommand(lease_duration_seconds=30),
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )
    first_hash = module.heartbeat_token_hash
    assert first_hash is not None
    assert first_token not in first_hash
    assert verify_module_token(first_token, first_hash)

    _, second_token = await issue_module_credential(
        cast(AsyncSession, session),
        module_id=module.id,
        command=ModuleCredentialCommand(lease_duration_seconds=45),
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )
    assert module.heartbeat_token_hash is not None
    assert not verify_module_token(first_token, module.heartbeat_token_hash)
    assert verify_module_token(second_token, module.heartbeat_token_hash)
    serialized_evidence = str(session.added)
    assert first_token not in serialized_evidence
    assert second_token not in serialized_evidence


@pytest.mark.asyncio
async def test_heartbeat_renews_lease_and_expiry_is_reconciled() -> None:
    module = PlatformModule(
        id=uuid4(),
        name="ecu-simulator",
        display_name="ECU Simulator",
        description="",
        version="1.0.0",
        base_url=None,
        status="registered",
        capabilities=[],
    )
    session = RegistrySession(module)
    _, token = await issue_module_credential(
        cast(AsyncSession, session),
        module_id=module.id,
        command=ModuleCredentialCommand(lease_duration_seconds=30),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    observed_at = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    await heartbeat_module(
        cast(AsyncSession, session),
        module_id=module.id,
        token=token,
        command=ModuleHeartbeat(status=ModuleStatus.DEGRADED, version="1.1.0"),
        correlation_id=uuid4(),
        now=observed_at,
    )
    assert module.status == "degraded"
    assert module.version == "1.1.0"
    assert module.last_seen_at == observed_at
    assert module.lease_expires_at == observed_at + timedelta(seconds=30)

    with pytest.raises(InvalidModuleCredentialError):
        await heartbeat_module(
            cast(AsyncSession, session),
            module_id=module.id,
            token="invalid-token-that-is-long-enough-for-the-contract",
            command=ModuleHeartbeat(),
            correlation_id=uuid4(),
            now=observed_at,
        )

    reconciled = await reconcile_expired_modules(
        cast(AsyncSession, session), now=observed_at + timedelta(seconds=31)
    )
    assert reconciled == 1
    assert module.status == "inactive"
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    assert [item.event_type for item in events] == [
        "atep.platform.module.credential-rotated.v1",
        "atep.platform.module.availability-changed.v1",
        "atep.platform.module.availability-changed.v1",
    ]
    lease_audit = [
        item
        for item in session.added
        if isinstance(item, AuditRecord) and item.action == "platform.module.lease_expired"
    ][0]
    assert lease_audit.actor_user_id is None
