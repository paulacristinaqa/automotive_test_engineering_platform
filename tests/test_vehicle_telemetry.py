from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import ModuleCapabilityRequiredError, TelemetryEventConflictError
from atep.core.security import hash_module_token
from atep.events.models import OutboxEvent
from atep.registry.models import ModuleCapability, PlatformModule
from atep.registry.service import authenticate_module
from atep.vehicles.models import Vehicle, VehicleTelemetryEvent
from atep.vehicles.schemas import TelemetryIngest, VehicleCreate
from atep.vehicles.service import create_vehicle, ingest_telemetry


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


class VehicleSession:
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


def vehicle() -> Vehicle:
    now = datetime.now(UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP Development Vehicle",
        model="EV Reference Platform",
        description="",
        status="registered",
        created_at=now,
        updated_at=now,
    )


def gateway_module(*, capability: bool = True) -> tuple[PlatformModule, str]:
    token = "gateway-token-that-is-longer-than-thirty-two-characters"
    capabilities = []
    if capability:
        capabilities.append(
            ModuleCapability(
                id=uuid4(),
                name="vehicle.telemetry.publish",
                version="1.0.0",
                description="Publish vehicle telemetry",
            )
        )
    module = PlatformModule(
        id=uuid4(),
        name="android-automotive-gateway",
        display_name="Android Automotive Gateway",
        description="",
        version="1.0.0",
        base_url=None,
        status="registered",
        heartbeat_token_hash=hash_module_token(token),
        capabilities=capabilities,
    )
    return module, token


def telemetry_command(*, value: float = 47.8) -> TelemetryIngest:
    return TelemetryIngest(
        event_id="01JXYZTELEMETRY0001",
        property="battery_temperature",
        value=value,
        unit="celsius",
        timestamp="2026-07-27T20:30:00Z",
        source="android-automotive",
    )


def test_vehicle_and_telemetry_contracts_normalize_and_reject_ambiguous_time() -> None:
    command = VehicleCreate(
        identifier=" Vehicle-001 ",
        display_name=" Development Vehicle ",
        model=" EV Reference Platform ",
    )
    assert command.identifier == "vehicle-001"
    assert command.display_name == "Development Vehicle"
    assert telemetry_command().property == "battery_temperature"
    with pytest.raises(ValidationError, match="UTC offset"):
        TelemetryIngest(
            event_id="01JXYZTELEMETRY0002",
            property="battery_temperature",
            value=47.8,
            timestamp="2026-07-27T20:30:00",
        )


@pytest.mark.asyncio
async def test_vehicle_registration_is_evented_and_audited_atomically() -> None:
    session = VehicleSession()
    registered = await create_vehicle(
        cast(AsyncSession, session),
        command=VehicleCreate(identifier="vehicle-001", display_name="Development Vehicle"),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert registered.identifier == "vehicle-001"
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.vehicle.registered.v1"
    ]
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "vehicle.registered"
    ]


@pytest.mark.asyncio
async def test_gateway_requires_valid_declared_telemetry_capability() -> None:
    module, token = gateway_module(capability=False)
    session = VehicleSession(module=module)
    with pytest.raises(ModuleCapabilityRequiredError):
        await authenticate_module(
            cast(AsyncSession, session),
            module_id=module.id,
            token=token,
            required_capability="vehicle.telemetry.publish",
        )


@pytest.mark.asyncio
async def test_telemetry_ingestion_is_atomic_and_exact_retry_is_idempotent() -> None:
    target = vehicle()
    module, _ = gateway_module()
    received_at = datetime(2026, 7, 27, 20, 30, 1, tzinfo=UTC)
    first_session = VehicleSession()
    event, duplicate = await ingest_telemetry(
        cast(AsyncSession, first_session),
        vehicle=target,
        module=module,
        command=telemetry_command(),
        correlation_id=uuid4(),
        received_at=received_at,
    )
    assert duplicate is False
    assert event.created_at == received_at
    outbox = [item for item in first_session.added if isinstance(item, OutboxEvent)]
    assert [item.event_type for item in outbox] == ["atep.vehicle.telemetry.received.v1"]
    assert outbox[0].payload["vehicle_id"] == "vehicle-001"

    retry_session = VehicleSession(scalar_values=[event])
    retried, duplicate = await ingest_telemetry(
        cast(AsyncSession, retry_session),
        vehicle=target,
        module=module,
        command=telemetry_command(),
        correlation_id=uuid4(),
    )
    assert retried is event
    assert duplicate is True
    assert not [item for item in retry_session.added if isinstance(item, OutboxEvent)]


@pytest.mark.asyncio
async def test_reused_event_id_with_different_payload_is_rejected() -> None:
    target = vehicle()
    module, _ = gateway_module()
    existing = VehicleTelemetryEvent(
        id=uuid4(),
        event_id="01JXYZTELEMETRY0001",
        vehicle_id=target.id,
        source_module_id=module.id,
        source="android-automotive",
        property_name="battery_temperature",
        value=47.8,
        unit="celsius",
        observed_at=datetime(2026, 7, 27, 20, 30, tzinfo=UTC),
        created_at=datetime.now(UTC),
    )
    session = VehicleSession(scalar_values=[existing])
    with pytest.raises(TelemetryEventConflictError):
        await ingest_telemetry(
            cast(AsyncSession, session),
            vehicle=target,
            module=module,
            command=telemetry_command(value=48.9),
            correlation_id=uuid4(),
        )
