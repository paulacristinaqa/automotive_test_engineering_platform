from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    DuplicateEcuIdentifierError,
    EcuStateVersionConflictError,
    ResourceNotFoundError,
)
from atep.ecus.models import ElectronicControlUnit
from atep.ecus.schemas import EcuCreate, EcuStatePayload, EcuStateReplace, EcuType
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


def ecu_state_payload(ecu: ElectronicControlUnit) -> EcuStatePayload:
    return EcuStatePayload.model_validate(
        {
            "operational_state": ecu.operational_state,
            "memory": ecu.memory,
            "faults": ecu.faults,
        }
    )


async def create_ecu(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: EcuCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> ElectronicControlUnit:
    existing = await session.scalar(
        select(ElectronicControlUnit).where(
            ElectronicControlUnit.vehicle_id == vehicle.id,
            ElectronicControlUnit.identifier == command.identifier,
        )
    )
    if existing is not None:
        raise DuplicateEcuIdentifierError()
    state = EcuStatePayload.model_validate(
        command.model_dump(exclude={"identifier", "display_name", "ecu_type"})
    )
    ecu = ElectronicControlUnit(
        vehicle_id=vehicle.id,
        identifier=command.identifier,
        display_name=command.display_name,
        ecu_type=command.ecu_type.value,
        operational_state=state.operational_state.value,
        memory=[item.model_dump(mode="json") for item in state.memory],
        faults=[item.model_dump(mode="json") for item in state.faults],
        version=1,
    )
    try:
        async with session.begin_nested():
            session.add(ecu)
            await session.flush()
    except IntegrityError as exc:
        raise DuplicateEcuIdentifierError() from exc
    evidence = _ecu_evidence(ecu, vehicle)
    enqueue_event(
        session,
        event_type="atep.ecu.created.v1",
        aggregate_type="ecu",
        aggregate_id=ecu.id,
        payload={**evidence, "state": state.model_dump(mode="json")},
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.created",
        resource_type="ecu",
        resource_id=ecu.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return ecu


async def require_ecu(
    session: AsyncSession, *, vehicle: Vehicle, identifier: str, for_update: bool = False
) -> ElectronicControlUnit:
    query = select(ElectronicControlUnit).where(
        ElectronicControlUnit.vehicle_id == vehicle.id,
        ElectronicControlUnit.identifier == identifier,
    )
    if for_update:
        query = query.with_for_update()
    ecu = await session.scalar(query)
    if ecu is None:
        raise ResourceNotFoundError("ecu")
    return ecu


async def list_ecus(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    limit: int,
    offset: int,
    ecu_type: EcuType | None = None,
) -> tuple[list[ElectronicControlUnit], int]:
    query = select(ElectronicControlUnit).where(ElectronicControlUnit.vehicle_id == vehicle.id)
    if ecu_type is not None:
        query = query.where(ElectronicControlUnit.ecu_type == ecu_type.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(ElectronicControlUnit.identifier, ElectronicControlUnit.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def replace_ecu_state(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: EcuStateReplace,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[ElectronicControlUnit, bool]:
    locked = await require_ecu(
        session, vehicle=vehicle, identifier=ecu.identifier, for_update=True
    )
    requested = EcuStatePayload.model_validate(command.model_dump(exclude={"expected_version"}))
    current = ecu_state_payload(locked)
    if command.expected_version != locked.version:
        if command.expected_version == locked.version - 1 and requested == current:
            return locked, True
        raise EcuStateVersionConflictError(current_version=locked.version)
    if requested == current:
        return locked, True
    previous_version = locked.version
    locked.operational_state = requested.operational_state.value
    locked.memory = [item.model_dump(mode="json") for item in requested.memory]
    locked.faults = [item.model_dump(mode="json") for item in requested.faults]
    locked.version += 1
    await session.flush()
    await session.refresh(locked, attribute_names=["updated_at"])
    evidence = {
        **_ecu_evidence(locked, vehicle),
        "previous_version": previous_version,
        "version": locked.version,
        "operational_state": locked.operational_state,
        "memory_cell_count": len(locked.memory),
        "fault_count": len(locked.faults),
    }
    enqueue_event(
        session,
        event_type="atep.ecu.state.updated.v1",
        aggregate_type="ecu",
        aggregate_id=locked.id,
        payload={**evidence, "state": requested.model_dump(mode="json")},
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.state_updated",
        resource_type="ecu",
        resource_id=locked.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return locked, False


def _ecu_evidence(ecu: ElectronicControlUnit, vehicle: Vehicle) -> dict[str, object]:
    return {
        "ecu_id": str(ecu.id),
        "ecu_identifier": ecu.identifier,
        "vehicle_id": vehicle.identifier,
        "ecu_type": ecu.ecu_type,
    }
