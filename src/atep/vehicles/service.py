from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    DuplicateVehicleIdentifierError,
    InvalidCommandClaimError,
    ModuleCapabilityRequiredError,
    ResourceNotFoundError,
    TelemetryEventConflictError,
    VehicleCommandConflictError,
    VehicleCommandStateError,
)
from atep.core.security import generate_module_token, hash_module_token, verify_module_token
from atep.events.outbox import enqueue_event
from atep.registry.models import PlatformModule
from atep.vehicles.models import Vehicle, VehicleCommand, VehicleTelemetryEvent
from atep.vehicles.schemas import (
    TelemetryIngest,
    VehicleCommandAcknowledge,
    VehicleCommandCreate,
    VehicleCommandStatus,
    VehicleCreate,
    VehicleStatus,
)

COMMAND_CONSUME_CAPABILITY = "vehicle.commands.consume"


async def create_vehicle(
    session: AsyncSession,
    *,
    command: VehicleCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> Vehicle:
    existing = await session.scalar(select(Vehicle).where(Vehicle.identifier == command.identifier))
    if existing is not None:
        raise DuplicateVehicleIdentifierError()
    vehicle = Vehicle(
        identifier=command.identifier,
        display_name=command.display_name,
        model=command.model,
        description=command.description,
        status=VehicleStatus.REGISTERED.value,
    )
    try:
        async with session.begin_nested():
            session.add(vehicle)
            await session.flush()
    except IntegrityError as exc:
        raise DuplicateVehicleIdentifierError() from exc
    payload = _vehicle_payload(vehicle)
    enqueue_event(
        session,
        event_type="atep.vehicle.registered.v1",
        aggregate_type="vehicle",
        aggregate_id=vehicle.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="vehicle.registered",
        resource_type="vehicle",
        resource_id=vehicle.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return vehicle


async def require_vehicle(session: AsyncSession, identifier: str) -> Vehicle:
    vehicle = await session.scalar(select(Vehicle).where(Vehicle.identifier == identifier))
    if vehicle is None:
        raise ResourceNotFoundError("vehicle")
    return vehicle


async def list_vehicles(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: VehicleStatus | None = None,
) -> tuple[list[Vehicle], int]:
    query = select(Vehicle)
    if status is not None:
        query = query.where(Vehicle.status == status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(Vehicle.identifier, Vehicle.id).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def update_vehicle_status(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    status: VehicleStatus,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> Vehicle:
    previous_status = vehicle.status
    vehicle.status = status.value
    await session.flush()
    await session.refresh(vehicle, attribute_names=["updated_at"])
    payload = {
        "vehicle_id": vehicle.identifier,
        "previous_status": previous_status,
        "status": vehicle.status,
    }
    enqueue_event(
        session,
        event_type="atep.vehicle.status-changed.v1",
        aggregate_type="vehicle",
        aggregate_id=vehicle.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="vehicle.status_changed",
        resource_type="vehicle",
        resource_id=vehicle.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return vehicle


async def ingest_telemetry(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    module: PlatformModule,
    command: TelemetryIngest,
    correlation_id: UUID | None,
    received_at: datetime | None = None,
) -> tuple[VehicleTelemetryEvent, bool]:
    existing = await session.scalar(
        select(VehicleTelemetryEvent).where(VehicleTelemetryEvent.event_id == command.event_id)
    )
    if existing is not None:
        if not _same_telemetry(existing, vehicle, module, command):
            raise TelemetryEventConflictError()
        return existing, True

    event = VehicleTelemetryEvent(
        event_id=command.event_id,
        vehicle_id=vehicle.id,
        source_module_id=module.id,
        source=command.source,
        property_name=command.property,
        value=command.value,
        unit=command.unit,
        observed_at=command.timestamp,
        created_at=received_at or datetime.now(UTC),
    )
    try:
        async with session.begin_nested():
            session.add(event)
            await session.flush()
    except IntegrityError:
        concurrent = await session.scalar(
            select(VehicleTelemetryEvent).where(VehicleTelemetryEvent.event_id == command.event_id)
        )
        if concurrent is None or not _same_telemetry(concurrent, vehicle, module, command):
            raise TelemetryEventConflictError() from None
        return concurrent, True

    enqueue_event(
        session,
        event_type="atep.vehicle.telemetry.received.v1",
        aggregate_type="vehicle",
        aggregate_id=vehicle.id,
        payload={
            "telemetry_id": str(event.id),
            "event_id": event.event_id,
            "vehicle_id": vehicle.identifier,
            "source_module_id": str(module.id),
            "source": command.source,
            "property": event.property_name,
            "value": event.value,
            "unit": event.unit,
            "timestamp": event.observed_at.isoformat(),
            "received_at": event.created_at.isoformat(),
        },
        correlation_id=correlation_id,
    )
    return event, False


async def list_telemetry(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    limit: int,
    offset: int,
    property_name: str | None = None,
) -> tuple[list[VehicleTelemetryEvent], int]:
    query = select(VehicleTelemetryEvent).where(VehicleTelemetryEvent.vehicle_id == vehicle.id)
    if property_name is not None:
        query = query.where(VehicleTelemetryEvent.property_name == property_name)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(VehicleTelemetryEvent.observed_at.desc(), VehicleTelemetryEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


def _same_telemetry(
    event: VehicleTelemetryEvent,
    vehicle: Vehicle,
    module: PlatformModule,
    command: TelemetryIngest,
) -> bool:
    return (
        event.vehicle_id == vehicle.id
        and event.source_module_id == module.id
        and event.source == command.source
        and event.property_name == command.property
        and event.value == command.value
        and event.unit == command.unit
        and event.observed_at == command.timestamp
    )


def _vehicle_payload(vehicle: Vehicle) -> dict[str, str]:
    return {
        "vehicle_id": vehicle.identifier,
        "display_name": vehicle.display_name,
        "model": vehicle.model,
        "description": vehicle.description,
        "status": vehicle.status,
    }


async def create_vehicle_command(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    actor_user_id: UUID,
    command: VehicleCommandCreate,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[VehicleCommand, bool]:
    existing = await session.scalar(
        select(VehicleCommand).where(VehicleCommand.command_id == command.command_id)
    )
    requested_at = now or datetime.now(UTC)
    available_at = command.available_at or (
        existing.available_at if existing is not None else requested_at
    )
    if existing is not None:
        if not _same_vehicle_command(existing, vehicle, actor_user_id, command, available_at):
            raise VehicleCommandConflictError()
        return existing, True

    target = await session.get(PlatformModule, command.target_module_id)
    if target is None:
        raise ResourceNotFoundError("module")
    if COMMAND_CONSUME_CAPABILITY not in {item.name for item in target.capabilities}:
        raise ModuleCapabilityRequiredError(COMMAND_CONSUME_CAPABILITY)

    queued = VehicleCommand(
        command_id=command.command_id,
        vehicle_id=vehicle.id,
        target_module_id=target.id,
        requested_by_user_id=actor_user_id,
        test_run_id=command.test_run_id,
        kind=command.kind.value,
        payload=command.parameters.model_dump(),
        status=VehicleCommandStatus.PENDING.value,
        attempt_count=0,
        available_at=available_at,
        leased_until=None,
        lease_token_hash=None,
        completed_at=None,
        result=None,
        error_code=None,
        error_message=None,
        created_at=requested_at,
        updated_at=requested_at,
    )
    try:
        async with session.begin_nested():
            session.add(queued)
            await session.flush()
    except IntegrityError as exc:
        raise VehicleCommandConflictError() from exc

    event_payload = _command_event_payload(queued, vehicle)
    enqueue_event(
        session,
        event_type="atep.vehicle.command.requested.v1",
        aggregate_type="vehicle_command",
        aggregate_id=queued.id,
        payload=event_payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="vehicle.command_requested",
        resource_type="vehicle_command",
        resource_id=queued.id,
        correlation_id=correlation_id,
        details=event_payload,
    )
    return queued, False


async def list_vehicle_commands(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    limit: int,
    offset: int,
    status: VehicleCommandStatus | None = None,
) -> tuple[list[VehicleCommand], int]:
    query = select(VehicleCommand).where(VehicleCommand.vehicle_id == vehicle.id)
    if status is not None:
        query = query.where(VehicleCommand.status == status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(VehicleCommand.created_at.desc(), VehicleCommand.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def claim_next_vehicle_command(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    module: PlatformModule,
    lease_seconds: int,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[VehicleCommand | None, str | None]:
    claimed_at = now or datetime.now(UTC)
    query = (
        select(VehicleCommand)
        .where(
            VehicleCommand.vehicle_id == vehicle.id,
            VehicleCommand.target_module_id == module.id,
            VehicleCommand.available_at <= claimed_at,
            or_(
                VehicleCommand.status == VehicleCommandStatus.PENDING.value,
                (
                    (VehicleCommand.status == VehicleCommandStatus.CLAIMED.value)
                    & (VehicleCommand.leased_until <= claimed_at)
                ),
            ),
        )
        .order_by(VehicleCommand.available_at, VehicleCommand.created_at, VehicleCommand.id)
        .with_for_update(skip_locked=True)
    )
    command = await session.scalar(query)
    if command is None:
        return None, None

    claim_token = generate_module_token()
    command.status = VehicleCommandStatus.CLAIMED.value
    command.attempt_count += 1
    command.leased_until = claimed_at + timedelta(seconds=lease_seconds)
    command.lease_token_hash = hash_module_token(claim_token)
    command.updated_at = claimed_at
    await session.flush()
    enqueue_event(
        session,
        event_type="atep.vehicle.command.claimed.v1",
        aggregate_type="vehicle_command",
        aggregate_id=command.id,
        payload={
            **_command_event_payload(command, vehicle),
            "attempt_count": command.attempt_count,
            "leased_until": command.leased_until.isoformat(),
        },
        correlation_id=correlation_id,
    )
    return command, claim_token


async def acknowledge_vehicle_command(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    module: PlatformModule,
    command_id: str,
    acknowledgement: VehicleCommandAcknowledge,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[VehicleCommand, bool]:
    command = await session.scalar(
        select(VehicleCommand).where(
            VehicleCommand.command_id == command_id,
            VehicleCommand.vehicle_id == vehicle.id,
            VehicleCommand.target_module_id == module.id,
        )
    )
    if command is None:
        raise ResourceNotFoundError("vehicle_command")
    if command.lease_token_hash is None or not verify_module_token(
        acknowledgement.claim_token, command.lease_token_hash
    ):
        raise InvalidCommandClaimError()

    terminal_statuses = {
        VehicleCommandStatus.SUCCEEDED.value,
        VehicleCommandStatus.FAILED.value,
        VehicleCommandStatus.REJECTED.value,
    }
    if command.status in terminal_statuses:
        if not _same_acknowledgement(command, acknowledgement):
            raise VehicleCommandStateError()
        return command, True
    if command.status != VehicleCommandStatus.CLAIMED.value:
        raise VehicleCommandStateError()

    completed_at = now or datetime.now(UTC)
    if command.leased_until is None or command.leased_until < completed_at:
        raise InvalidCommandClaimError()
    command.status = acknowledgement.outcome.value
    command.result = acknowledgement.result
    command.error_code = acknowledgement.error_code
    command.error_message = acknowledgement.error_message
    command.completed_at = completed_at
    command.leased_until = None
    command.updated_at = completed_at
    await session.flush()
    enqueue_event(
        session,
        event_type="atep.vehicle.command.completed.v1",
        aggregate_type="vehicle_command",
        aggregate_id=command.id,
        payload={
            **_command_event_payload(command, vehicle),
            "result": command.result,
            "error_code": command.error_code,
            "error_message": command.error_message,
            "completed_at": completed_at.isoformat(),
        },
        correlation_id=correlation_id,
    )
    return command, False


def _same_vehicle_command(
    existing: VehicleCommand,
    vehicle: Vehicle,
    actor_user_id: UUID,
    command: VehicleCommandCreate,
    available_at: datetime,
) -> bool:
    return (
        existing.vehicle_id == vehicle.id
        and existing.target_module_id == command.target_module_id
        and existing.requested_by_user_id == actor_user_id
        and existing.test_run_id == command.test_run_id
        and existing.kind == command.kind.value
        and existing.payload == command.parameters.model_dump()
        and existing.available_at == available_at
    )


def _same_acknowledgement(
    command: VehicleCommand, acknowledgement: VehicleCommandAcknowledge
) -> bool:
    return (
        command.status == acknowledgement.outcome.value
        and command.result == acknowledgement.result
        and command.error_code == acknowledgement.error_code
        and command.error_message == acknowledgement.error_message
    )


def _command_event_payload(command: VehicleCommand, vehicle: Vehicle) -> dict[str, object]:
    return {
        "command_id": command.command_id,
        "vehicle_id": vehicle.identifier,
        "target_module_id": str(command.target_module_id),
        "requested_by_user_id": str(command.requested_by_user_id),
        "test_run_id": command.test_run_id,
        "kind": command.kind,
        "parameters": command.payload,
        "status": command.status,
    }
