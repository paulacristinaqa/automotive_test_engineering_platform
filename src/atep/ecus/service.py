from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    DuplicateEcuIdentifierError,
    EcuExecutionStateError,
    EcuSimulationCommandConflictError,
    EcuStateVersionConflictError,
    ResourceNotFoundError,
)
from atep.ecus.models import EcuSimulationCommand, ElectronicControlUnit
from atep.ecus.schemas import (
    EcuAdvanceCommand,
    EcuCreate,
    EcuOperationalState,
    EcuResetCommand,
    EcuResetMode,
    EcuStatePayload,
    EcuStateReplace,
    EcuTaskRunSummary,
    EcuType,
)
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


def ecu_state_payload(ecu: ElectronicControlUnit) -> EcuStatePayload:
    return EcuStatePayload.model_validate(
        {
            "operational_state": ecu.operational_state,
            "memory": ecu.memory,
            "faults": ecu.faults,
            "cyclic_tasks": ecu.cyclic_tasks,
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
        cyclic_tasks=[item.model_dump(mode="json") for item in state.cyclic_tasks],
        version=1,
        simulation_time_ms=0,
        boot_count=0,
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
    locked.cyclic_tasks = [item.model_dump(mode="json") for item in requested.cyclic_tasks]
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
        "cyclic_task_count": len(locked.cyclic_tasks),
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


def _task_run_summary(
    *, task_id: str, period_ms: int, offset_ms: int, start_ms: int, end_ms: int
) -> EcuTaskRunSummary:
    first_schedule = offset_ms if offset_ms > 0 else period_ms

    def executions_at_or_before(time_ms: int) -> int:
        if time_ms < first_schedule:
            return 0
        return ((time_ms - first_schedule) // period_ms) + 1

    previous_count = executions_at_or_before(start_ms)
    total_count = executions_at_or_before(end_ms)
    execution_count = total_count - previous_count
    if execution_count == 0:
        return EcuTaskRunSummary(
            task_id=task_id, execution_count=0, first_due_ms=None, last_due_ms=None
        )
    first_due_ms = first_schedule + (previous_count * period_ms)
    last_due_ms = first_schedule + ((total_count - 1) * period_ms)
    return EcuTaskRunSummary(
        task_id=task_id,
        execution_count=execution_count,
        first_due_ms=first_due_ms,
        last_due_ms=last_due_ms,
    )


async def execute_ecu_advance(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: EcuAdvanceCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[EcuSimulationCommand, bool]:
    locked = await require_ecu(
        session, vehicle=vehicle, identifier=ecu.identifier, for_update=True
    )
    request_payload = command.model_dump(mode="json")
    existing = await _existing_simulation_command(
        session, ecu=locked, command_id=command.command_id
    )
    if existing is not None:
        if existing.kind == "advance" and existing.request == request_payload:
            return existing, True
        raise EcuSimulationCommandConflictError()
    if command.expected_version != locked.version:
        raise EcuStateVersionConflictError(current_version=locked.version)
    if locked.operational_state not in {
        EcuOperationalState.RUNNING.value,
        EcuOperationalState.DEGRADED.value,
    }:
        raise EcuExecutionStateError(current_state=locked.operational_state)

    previous_version = locked.version
    previous_time_ms = locked.simulation_time_ms
    simulation_time_ms = previous_time_ms + command.duration_ms
    state = ecu_state_payload(locked)
    summaries = [
        _task_run_summary(
            task_id=task.task_id,
            period_ms=task.period_ms,
            offset_ms=task.offset_ms,
            start_ms=previous_time_ms,
            end_ms=simulation_time_ms,
        )
        for task in sorted(state.cyclic_tasks, key=lambda item: item.task_id)
    ]
    result = {
        "duration_ms": command.duration_ms,
        "task_runs": [item.model_dump(mode="json") for item in summaries],
    }
    locked.simulation_time_ms = simulation_time_ms
    locked.version += 1
    execution = EcuSimulationCommand(
        ecu_id=locked.id,
        command_id=command.command_id,
        kind="advance",
        request=request_payload,
        result=result,
        previous_version=previous_version,
        state_version=locked.version,
        previous_time_ms=previous_time_ms,
        simulation_time_ms=simulation_time_ms,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    evidence = _simulation_evidence(execution, locked, vehicle)
    enqueue_event(
        session,
        event_type="atep.ecu.simulation.advanced.v1",
        aggregate_type="ecu",
        aggregate_id=locked.id,
        payload={**evidence, **result},
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.simulation_advanced",
        resource_type="ecu",
        resource_id=locked.id,
        correlation_id=correlation_id,
        details={
            **evidence,
            "duration_ms": command.duration_ms,
            "task_count": len(summaries),
            "execution_count": sum(item.execution_count for item in summaries),
        },
    )
    return execution, False


_RESET_DURATION_MS = {
    EcuResetMode.SOFT: 10,
    EcuResetMode.HARD: 100,
    EcuResetMode.POWER_CYCLE: 500,
}


async def execute_ecu_reset(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: EcuResetCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[EcuSimulationCommand, bool]:
    locked = await require_ecu(
        session, vehicle=vehicle, identifier=ecu.identifier, for_update=True
    )
    request_payload = command.model_dump(mode="json")
    existing = await _existing_simulation_command(
        session, ecu=locked, command_id=command.command_id
    )
    if existing is not None:
        if existing.kind == "reset" and existing.request == request_payload:
            return existing, True
        raise EcuSimulationCommandConflictError()
    if command.expected_version != locked.version:
        raise EcuStateVersionConflictError(current_version=locked.version)

    duration_ms = _RESET_DURATION_MS[command.mode]
    previous_version = locked.version
    previous_time_ms = locked.simulation_time_ms
    state = ecu_state_payload(locked)
    has_confirmed_critical_fault = any(
        fault.severity.value == "critical" and fault.status.value == "confirmed"
        for fault in state.faults
    )
    locked.operational_state = (
        EcuOperationalState.FAULT.value
        if has_confirmed_critical_fault
        else EcuOperationalState.OFFLINE.value
    )
    locked.simulation_time_ms += duration_ms
    locked.boot_count += 1
    locked.version += 1
    result = {
        "mode": command.mode.value,
        "reset_duration_ms": duration_ms,
        "boot_count": locked.boot_count,
        "memory_preserved": True,
        "faults_preserved": True,
    }
    execution = EcuSimulationCommand(
        ecu_id=locked.id,
        command_id=command.command_id,
        kind="reset",
        request=request_payload,
        result=result,
        previous_version=previous_version,
        state_version=locked.version,
        previous_time_ms=previous_time_ms,
        simulation_time_ms=locked.simulation_time_ms,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    evidence = _simulation_evidence(execution, locked, vehicle)
    enqueue_event(
        session,
        event_type="atep.ecu.reset.completed.v1",
        aggregate_type="ecu",
        aggregate_id=locked.id,
        payload={**evidence, **result},
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.reset_completed",
        resource_type="ecu",
        resource_id=locked.id,
        correlation_id=correlation_id,
        details={**evidence, **result},
    )
    return execution, False


async def _existing_simulation_command(
    session: AsyncSession, *, ecu: ElectronicControlUnit, command_id: str
) -> EcuSimulationCommand | None:
    existing: EcuSimulationCommand | None = await session.scalar(
        select(EcuSimulationCommand).where(
            EcuSimulationCommand.ecu_id == ecu.id,
            EcuSimulationCommand.command_id == command_id,
        )
    )
    return existing


def _simulation_evidence(
    command: EcuSimulationCommand, ecu: ElectronicControlUnit, vehicle: Vehicle
) -> dict[str, object]:
    return {
        **_ecu_evidence(ecu, vehicle),
        "command_id": command.command_id,
        "previous_version": command.previous_version,
        "version": command.state_version,
        "previous_time_ms": command.previous_time_ms,
        "simulation_time_ms": command.simulation_time_ms,
    }


def _ecu_evidence(ecu: ElectronicControlUnit, vehicle: Vehicle) -> dict[str, object]:
    return {
        "ecu_id": str(ecu.id),
        "ecu_identifier": ecu.identifier,
        "vehicle_id": vehicle.identifier,
        "ecu_type": ecu.ecu_type,
    }
