from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import InvalidCommandClaimError, VehicleCommandConflictError
from atep.core.security import hash_module_token
from atep.events.models import OutboxEvent
from atep.registry.models import ModuleCapability, PlatformModule
from atep.vehicles.models import Vehicle, VehicleCommand
from atep.vehicles.schemas import (
    VehicleCommandAcknowledge,
    VehicleCommandCreate,
    VehicleCommandOutcome,
    VehicleCommandParameters,
)
from atep.vehicles.service import (
    acknowledge_vehicle_command,
    claim_next_vehicle_command,
    create_vehicle_command,
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


class CommandSession:
    def __init__(
        self,
        *,
        module: PlatformModule | None = None,
        scalar_values: list[Any] | None = None,
    ) -> None:
        self.module = module
        self.scalar_values = list(scalar_values or [])
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def get(self, model: type[Any], _: object) -> Any:
        return self.module if model is PlatformModule else None

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    async def execute(self, _: Any) -> Any:
        raise AssertionError("execute was not expected")


def vehicle() -> Vehicle:
    now = datetime.now(UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP Development Vehicle",
        model="EV Reference Platform",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def gateway_module() -> PlatformModule:
    return PlatformModule(
        id=uuid4(),
        name="android-automotive-gateway",
        display_name="Android Automotive Gateway",
        description="",
        version="1.0.0",
        base_url=None,
        status="active",
        heartbeat_token_hash=hash_module_token("module-token-longer-than-thirty-two-characters"),
        capabilities=[
            ModuleCapability(
                id=uuid4(),
                name="vehicle.commands.consume",
                version="1.0.0",
                description="Consume vehicle commands",
            )
        ],
    )


def create_contract(module_id: UUID, *, value: int = 50) -> VehicleCommandCreate:
    return VehicleCommandCreate(
        command_id="01JXYZCOMMAND0001",
        target_module_id=module_id,
        test_run_id="01JXYZTESTRUN0001",
        parameters=VehicleCommandParameters(property="battery_level", value=value),
    )


def queued_command(
    target: Vehicle,
    module: PlatformModule,
    actor_id: UUID,
    *,
    status: str = "pending",
) -> VehicleCommand:
    now = datetime(2026, 8, 4, 20, 0, tzinfo=UTC)
    return VehicleCommand(
        id=uuid4(),
        command_id="01JXYZCOMMAND0001",
        vehicle_id=target.id,
        target_module_id=module.id,
        requested_by_user_id=actor_id,
        test_run_id="01JXYZTESTRUN0001",
        kind="set_property",
        payload={"property": "battery_level", "value": 50},
        status=status,
        attempt_count=0,
        available_at=now,
        leased_until=None,
        lease_token_hash=None,
        completed_at=None,
        result=None,
        error_code=None,
        error_message=None,
        created_at=now,
        updated_at=now,
    )


def test_command_contract_rejects_ambiguous_time_and_incomplete_failure() -> None:
    module_id = uuid4()
    with pytest.raises(ValidationError, match="UTC offset"):
        VehicleCommandCreate(
            command_id="01JXYZCOMMAND0001",
            target_module_id=module_id,
            parameters={"property": "battery_level", "value": 50},
            available_at="2026-08-04T20:00:00",
        )
    with pytest.raises(ValidationError, match="require an error code"):
        VehicleCommandAcknowledge(
            claim_token="claim-token-that-is-longer-than-thirty-two-characters",
            outcome=VehicleCommandOutcome.FAILED,
        )


@pytest.mark.asyncio
async def test_command_request_is_idempotent_audited_and_evented() -> None:
    target = vehicle()
    module = gateway_module()
    actor_id = uuid4()
    requested_at = datetime(2026, 8, 4, 20, 0, tzinfo=UTC)
    session = CommandSession(module=module)
    command, duplicate = await create_vehicle_command(
        cast(AsyncSession, session),
        vehicle=target,
        actor_user_id=actor_id,
        command=create_contract(module.id),
        correlation_id=uuid4(),
        now=requested_at,
    )
    assert duplicate is False
    assert command.available_at == requested_at
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.vehicle.command.requested.v1"
    ]
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "vehicle.command_requested"
    ]

    retry_session = CommandSession(scalar_values=[command])
    retried, duplicate = await create_vehicle_command(
        cast(AsyncSession, retry_session),
        vehicle=target,
        actor_user_id=actor_id,
        command=create_contract(module.id),
        correlation_id=uuid4(),
        now=requested_at + timedelta(minutes=1),
    )
    assert retried is command
    assert duplicate is True
    assert retry_session.added == []

    conflict_session = CommandSession(scalar_values=[command])
    with pytest.raises(VehicleCommandConflictError):
        await create_vehicle_command(
            cast(AsyncSession, conflict_session),
            vehicle=target,
            actor_user_id=actor_id,
            command=create_contract(module.id, value=60),
            correlation_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_claim_uses_hashed_token_lease_and_attempt_counter() -> None:
    target = vehicle()
    module = gateway_module()
    command = queued_command(target, module, uuid4())
    now = datetime(2026, 8, 4, 20, 1, tzinfo=UTC)
    session = CommandSession(scalar_values=[command])
    claimed, token = await claim_next_vehicle_command(
        cast(AsyncSession, session),
        vehicle=target,
        module=module,
        lease_seconds=60,
        correlation_id=uuid4(),
        now=now,
    )
    assert claimed is command
    assert token is not None
    assert command.lease_token_hash is not None
    assert token not in command.lease_token_hash
    assert command.lease_token_hash == hash_module_token(token)
    assert command.leased_until == now + timedelta(seconds=60)
    assert command.attempt_count == 1
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.vehicle.command.claimed.v1"
    ]


@pytest.mark.asyncio
async def test_acknowledgement_is_authenticated_evented_and_idempotent() -> None:
    target = vehicle()
    module = gateway_module()
    command = queued_command(target, module, uuid4(), status="claimed")
    claim_token = "claim-token-that-is-longer-than-thirty-two-characters"
    command.lease_token_hash = hash_module_token(claim_token)
    command.leased_until = datetime(2026, 8, 4, 20, 3, tzinfo=UTC)
    acknowledgement = VehicleCommandAcknowledge(
        claim_token=claim_token,
        outcome=VehicleCommandOutcome.SUCCEEDED,
        result={"property": "battery_level", "applied": True},
    )
    completed_at = datetime(2026, 8, 4, 20, 2, tzinfo=UTC)
    session = CommandSession(scalar_values=[command])
    completed, duplicate = await acknowledge_vehicle_command(
        cast(AsyncSession, session),
        vehicle=target,
        module=module,
        command_id=command.command_id,
        acknowledgement=acknowledgement,
        correlation_id=uuid4(),
        now=completed_at,
    )
    assert duplicate is False
    assert completed.status == "succeeded"
    assert completed.completed_at == completed_at
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.vehicle.command.completed.v1"
    ]

    retry_session = CommandSession(scalar_values=[command])
    _, duplicate = await acknowledge_vehicle_command(
        cast(AsyncSession, retry_session),
        vehicle=target,
        module=module,
        command_id=command.command_id,
        acknowledgement=acknowledgement,
        correlation_id=uuid4(),
    )
    assert duplicate is True
    assert retry_session.added == []

    invalid_session = CommandSession(scalar_values=[command])
    invalid = acknowledgement.model_copy(update={"claim_token": "x" * 48})
    with pytest.raises(InvalidCommandClaimError):
        await acknowledge_vehicle_command(
            cast(AsyncSession, invalid_session),
            vehicle=target,
            module=module,
            command_id=command.command_id,
            acknowledgement=invalid,
            correlation_id=uuid4(),
        )
