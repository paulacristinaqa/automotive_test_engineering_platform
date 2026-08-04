from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    DuplicateVehicleIdentifierError,
    ResourceNotFoundError,
    TelemetryEventConflictError,
)
from atep.events.outbox import enqueue_event
from atep.registry.models import PlatformModule
from atep.vehicles.models import Vehicle, VehicleTelemetryEvent
from atep.vehicles.schemas import TelemetryIngest, VehicleCreate, VehicleStatus


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
