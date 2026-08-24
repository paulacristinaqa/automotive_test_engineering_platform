import hashlib
import json
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    DuplicateEcuIdentifierError,
    DuplicateEcuSignalRouteError,
    EcuExecutionStateError,
    EcuFaultContractError,
    EcuMemoryContractError,
    EcuProfileContractError,
    EcuSignalContractError,
    EcuSimulationCommandConflictError,
    EcuStateVersionConflictError,
    ResourceNotFoundError,
)
from atep.ecus.models import (
    EcuMemorySnapshot,
    EcuSignalRoute,
    EcuSimulationCommand,
    ElectronicControlUnit,
)
from atep.ecus.profiles import behavior_profile, execute_profile_transitions
from atep.ecus.schemas import (
    EcuAdvanceCommand,
    EcuCreate,
    EcuDtcCandidate,
    EcuFault,
    EcuFaultClearCommand,
    EcuFaultObservationCommand,
    EcuFaultSeverity,
    EcuFaultStatus,
    EcuMemoryCorruptionCommand,
    EcuMemoryRegion,
    EcuMemoryRegionKind,
    EcuOperationalState,
    EcuResetCommand,
    EcuResetMode,
    EcuSignalContract,
    EcuSignalDirection,
    EcuSignalPublishCommand,
    EcuSignalRouteCreate,
    EcuSignalRouteTransferCommand,
    EcuSnapshotCreate,
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
            "memory_regions": ecu.memory_regions,
            "faults": ecu.faults,
            "signals": ecu.signals or [],
            "cyclic_tasks": ecu.cyclic_tasks,
            "behavior_state": ecu.behavior_state,
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
    requested_state = EcuStatePayload.model_validate(
        command.model_dump(exclude={"identifier", "display_name", "ecu_type"})
    )
    profile = behavior_profile(command.ecu_type)
    state = _profile_state(
        requested_state,
        ecu_type=command.ecu_type,
        use_profile_defaults=not requested_state.cyclic_tasks,
    )
    state = _memory_state(state, use_default_region=not state.memory_regions)
    ecu = ElectronicControlUnit(
        vehicle_id=vehicle.id,
        identifier=command.identifier,
        display_name=command.display_name,
        ecu_type=command.ecu_type.value,
        operational_state=state.operational_state.value,
        memory=[item.model_dump(mode="json") for item in state.memory],
        memory_regions=[item.model_dump(mode="json") for item in state.memory_regions],
        faults=[item.model_dump(mode="json") for item in state.faults],
        signals=[item.model_dump(mode="json") for item in state.signals],
        cyclic_tasks=[item.model_dump(mode="json") for item in state.cyclic_tasks],
        profile_version=profile.profile_version,
        behavior_state=state.behavior_state,
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
    requested = _profile_state(
        requested, ecu_type=EcuType(locked.ecu_type), use_profile_defaults=False
    )
    current = ecu_state_payload(locked)
    if not requested.memory_regions:
        requested = requested.model_copy(update={"memory_regions": current.memory_regions})
    if "signals" not in command.model_fields_set:
        requested = requested.model_copy(update={"signals": current.signals})
    requested = _memory_state(requested, use_default_region=False)
    if command.expected_version != locked.version:
        if command.expected_version == locked.version - 1 and requested == current:
            return locked, True
        raise EcuStateVersionConflictError(current_version=locked.version)
    if requested == current:
        return locked, True
    previous_version = locked.version
    locked.operational_state = requested.operational_state.value
    locked.memory = [item.model_dump(mode="json") for item in requested.memory]
    locked.memory_regions = [
        item.model_dump(mode="json") for item in requested.memory_regions
    ]
    locked.faults = [item.model_dump(mode="json") for item in requested.faults]
    locked.signals = [item.model_dump(mode="json") for item in requested.signals]
    locked.cyclic_tasks = [item.model_dump(mode="json") for item in requested.cyclic_tasks]
    locked.behavior_state = requested.behavior_state
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
    profile = behavior_profile(EcuType(locked.ecu_type))
    locked.behavior_state = execute_profile_transitions(
        profile, locked.behavior_state, summaries
    )
    result["profile_version"] = locked.profile_version
    result["behavior_state"] = locked.behavior_state
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
            "profile_version": locked.profile_version,
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
    volatile_cells_reset = 0
    non_volatile_cells_preserved = 0
    regions = [EcuMemoryRegion.model_validate(item) for item in locked.memory_regions] or [
        EcuMemoryRegion(
            name="legacy_nvm",
            kind=EcuMemoryRegionKind.NON_VOLATILE,
            start_address=0,
            size=65_536,
        )
    ]
    memory = [dict(item) for item in locked.memory]
    for cell in memory:
        region = next(
            region
            for region in regions
            if region.start_address <= int(cell["address"]) < region.start_address + region.size
        )
        if region.kind is EcuMemoryRegionKind.NON_VOLATILE:
            non_volatile_cells_preserved += 1
        elif command.mode is not EcuResetMode.SOFT and int(cell["value"]) != region.reset_value:
            cell["value"] = region.reset_value
            volatile_cells_reset += 1
    locked.memory = memory
    locked.simulation_time_ms += duration_ms
    locked.boot_count += 1
    locked.version += 1
    result = {
        "mode": command.mode.value,
        "reset_duration_ms": duration_ms,
        "boot_count": locked.boot_count,
        "memory_preserved": volatile_cells_reset == 0,
        "volatile_cells_reset": volatile_cells_reset,
        "non_volatile_cells_preserved": non_volatile_cells_preserved,
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


async def create_memory_snapshot(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: EcuSnapshotCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> EcuMemorySnapshot:
    locked = await require_ecu(
        session, vehicle=vehicle, identifier=ecu.identifier, for_update=True
    )
    canonical_memory = sorted(locked.memory, key=lambda item: int(item["address"]))
    checksum = hashlib.sha256(
        json.dumps(canonical_memory, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    snapshot = EcuMemorySnapshot(
        ecu_id=locked.id,
        name=command.name,
        memory=canonical_memory,
        state_version=locked.version,
        simulation_time_ms=locked.simulation_time_ms,
        checksum_sha256=checksum,
        created_by_user_id=actor_user_id,
    )
    session.add(snapshot)
    await session.flush()
    evidence = {
        **_ecu_evidence(locked, vehicle),
        "snapshot_id": str(snapshot.id),
        "snapshot_name": snapshot.name,
        "state_version": snapshot.state_version,
        "memory_cell_count": len(snapshot.memory),
        "checksum_sha256": snapshot.checksum_sha256,
    }
    enqueue_event(
        session,
        event_type="atep.ecu.memory.snapshot.created.v1",
        aggregate_type="ecu",
        aggregate_id=locked.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.memory_snapshot_created",
        resource_type="ecu",
        resource_id=locked.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return snapshot


async def list_memory_snapshots(
    session: AsyncSession, *, ecu: ElectronicControlUnit, limit: int, offset: int
) -> tuple[list[EcuMemorySnapshot], int]:
    query = select(EcuMemorySnapshot).where(EcuMemorySnapshot.ecu_id == ecu.id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(EcuMemorySnapshot.created_at.desc(), EcuMemorySnapshot.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def require_memory_snapshot(
    session: AsyncSession, *, ecu: ElectronicControlUnit, snapshot_id: UUID
) -> EcuMemorySnapshot:
    snapshot = await session.scalar(
        select(EcuMemorySnapshot).where(
            EcuMemorySnapshot.ecu_id == ecu.id, EcuMemorySnapshot.id == snapshot_id
        )
    )
    if snapshot is None:
        raise ResourceNotFoundError("ecu memory snapshot")
    return snapshot


async def restore_memory_snapshot(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    snapshot: EcuMemorySnapshot,
    expected_version: int,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> ElectronicControlUnit:
    locked = await require_ecu(
        session, vehicle=vehicle, identifier=ecu.identifier, for_update=True
    )
    if expected_version != locked.version:
        raise EcuStateVersionConflictError(current_version=locked.version)
    EcuStatePayload.model_validate(
        {**ecu_state_payload(locked).model_dump(mode="json"), "memory": snapshot.memory}
    )
    previous_version = locked.version
    locked.memory = [dict(item) for item in snapshot.memory]
    locked.version += 1
    await session.flush()
    evidence = {
        **_ecu_evidence(locked, vehicle),
        "snapshot_id": str(snapshot.id),
        "previous_version": previous_version,
        "version": locked.version,
        "memory_cell_count": len(locked.memory),
        "checksum_sha256": snapshot.checksum_sha256,
    }
    enqueue_event(
        session,
        event_type="atep.ecu.memory.snapshot.restored.v1",
        aggregate_type="ecu",
        aggregate_id=locked.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.memory_snapshot_restored",
        resource_type="ecu",
        resource_id=locked.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return locked


async def corrupt_ecu_memory(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: EcuMemoryCorruptionCommand,
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
        if existing.kind == "memory_corruption" and existing.request == request_payload:
            return existing, True
        raise EcuSimulationCommandConflictError()
    if command.expected_version != locked.version:
        raise EcuStateVersionConflictError(current_version=locked.version)
    regions = [EcuMemoryRegion.model_validate(item) for item in locked.memory_regions] or [
        EcuMemoryRegion(
            name="legacy_nvm",
            kind=EcuMemoryRegionKind.NON_VOLATILE,
            start_address=0,
            size=65_536,
        )
    ]
    known_names = {region.name for region in regions}
    unknown_names = set(command.region_names) - known_names
    if unknown_names:
        raise EcuMemoryContractError(reason=f"unknown region: {sorted(unknown_names)[0]}")
    selected_names = set(command.region_names) or known_names
    candidates = sorted(
        (
            dict(cell)
            for cell in locked.memory
            if any(
                region.name in selected_names
                and region.start_address
                <= int(cell["address"])
                < region.start_address + region.size
                for region in regions
            )
        ),
        key=lambda item: int(item["address"]),
    )
    if not candidates:
        raise EcuMemoryContractError(reason="no initialized cells in selected regions")
    changes: list[dict[str, int]] = []
    memory_by_address = {int(cell["address"]): cell for cell in locked.memory}
    for index in range(command.bit_flips):
        digest = hashlib.sha256(f"{command.seed}:{index}".encode()).digest()
        candidate = candidates[int.from_bytes(digest[:4], "big") % len(candidates)]
        address = int(candidate["address"])
        bit = digest[4] % 8
        target = memory_by_address[address]
        previous_value = int(target["value"])
        value = previous_value ^ (1 << bit)
        target["value"] = value
        changes.append(
            {"address": address, "previous_value": previous_value, "value": value, "bit": bit}
        )
    previous_version = locked.version
    locked.memory = list(memory_by_address.values())
    locked.version += 1
    result: dict[str, object] = {
        "seed": command.seed,
        "requested_bit_flips": command.bit_flips,
        "changes": changes,
    }
    execution = EcuSimulationCommand(
        ecu_id=locked.id,
        command_id=command.command_id,
        kind="memory_corruption",
        request=request_payload,
        result=result,
        previous_version=previous_version,
        state_version=locked.version,
        previous_time_ms=locked.simulation_time_ms,
        simulation_time_ms=locked.simulation_time_ms,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    evidence = _simulation_evidence(execution, locked, vehicle)
    enqueue_event(
        session,
        event_type="atep.ecu.memory.corrupted.v1",
        aggregate_type="ecu",
        aggregate_id=locked.id,
        payload={**evidence, **result},
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.memory_corrupted",
        resource_type="ecu",
        resource_id=locked.id,
        correlation_id=correlation_id,
        details={**evidence, "seed": command.seed, "bit_flips": command.bit_flips},
    )
    return execution, False


async def observe_ecu_fault(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: EcuFaultObservationCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[EcuSimulationCommand, bool]:
    locked = await require_ecu(
        session, vehicle=vehicle, identifier=ecu.identifier, for_update=True
    )
    request_payload = command.model_dump(mode="json")
    existing_command = await _existing_simulation_command(
        session, ecu=locked, command_id=command.command_id
    )
    if existing_command is not None:
        if (
            existing_command.kind == "fault_observation"
            and existing_command.request == request_payload
        ):
            return existing_command, True
        raise EcuSimulationCommandConflictError()
    if command.expected_version != locked.version:
        raise EcuStateVersionConflictError(current_version=locked.version)

    faults = [EcuFault.model_validate(item) for item in locked.faults]
    current = next((item for item in faults if item.code == command.code), None)
    if current is not None and current.status is not EcuFaultStatus.HEALED:
        policy = (
            current.severity,
            current.confirmation_threshold,
            current.healing_threshold,
            current.latched,
        )
        requested_policy = (
            command.severity,
            command.confirmation_threshold,
            command.healing_threshold,
            command.latched,
        )
        if policy != requested_policy:
            raise EcuFaultContractError(reason="active fault policy cannot be changed")
    if current is None and not command.detected:
        raise EcuFaultContractError(reason="cannot heal an unknown fault")

    now_ms = locked.simulation_time_ms
    transition = "observed_absent"
    if current is None or current.status is EcuFaultStatus.HEALED:
        if not command.detected:
            raise EcuFaultContractError(reason="a healed fault requires a new detection")
        occurrence_count = 1
        confirmed = occurrence_count >= command.confirmation_threshold
        current = EcuFault(
            code=command.code,
            severity=command.severity,
            status=EcuFaultStatus.CONFIRMED if confirmed else EcuFaultStatus.PENDING,
            description=command.description,
            active=True,
            latched=command.latched,
            occurrence_count=occurrence_count,
            healing_count=0,
            confirmation_threshold=command.confirmation_threshold,
            healing_threshold=command.healing_threshold,
            first_seen_ms=now_ms,
            last_seen_ms=now_ms,
            confirmed_at_ms=now_ms if confirmed else None,
        )
        faults = [item for item in faults if item.code != command.code] + [current]
        transition = "confirmed" if confirmed else "pending"
    elif command.detected:
        occurrence_count = current.occurrence_count + 1
        confirmed = (
            current.status is EcuFaultStatus.CONFIRMED
            or occurrence_count >= current.confirmation_threshold
        )
        transition = (
            "confirmed"
            if confirmed and current.status is not EcuFaultStatus.CONFIRMED
            else "detected"
        )
        current = current.model_copy(
            update={
                "status": EcuFaultStatus.CONFIRMED if confirmed else EcuFaultStatus.PENDING,
                "active": True,
                "occurrence_count": occurrence_count,
                "healing_count": 0,
                "last_seen_ms": now_ms,
                "confirmed_at_ms": now_ms if transition == "confirmed" else current.confirmed_at_ms,
                "healed_at_ms": None,
            }
        )
        faults = [current if item.code == command.code else item for item in faults]
    else:
        healing_count = current.healing_count + 1
        may_heal = not (current.latched and current.status is EcuFaultStatus.CONFIRMED)
        healed = may_heal and healing_count >= current.healing_threshold
        transition = "healed" if healed else ("latched" if not may_heal else "healing")
        current = current.model_copy(
            update={
                "status": EcuFaultStatus.HEALED if healed else current.status,
                "active": not healed,
                "occurrence_count": (
                    0 if current.status is EcuFaultStatus.PENDING else current.occurrence_count
                ),
                "healing_count": healing_count,
                "healed_at_ms": now_ms if healed else None,
            }
        )
        faults = [current if item.code == command.code else item for item in faults]

    previous_version = locked.version
    locked.faults = [item.model_dump(mode="json") for item in faults]
    _apply_fault_operational_state(locked, faults)
    locked.version += 1
    result = {"transition": transition, "fault": current.model_dump(mode="json")}
    execution = EcuSimulationCommand(
        ecu_id=locked.id,
        command_id=command.command_id,
        kind="fault_observation",
        request=request_payload,
        result=result,
        previous_version=previous_version,
        state_version=locked.version,
        previous_time_ms=now_ms,
        simulation_time_ms=now_ms,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    _record_fault_evidence(
        session,
        execution=execution,
        ecu=locked,
        vehicle=vehicle,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
    )
    return execution, False


async def clear_ecu_fault(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    fault_code: str,
    command: EcuFaultClearCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[EcuSimulationCommand, bool]:
    locked = await require_ecu(
        session, vehicle=vehicle, identifier=ecu.identifier, for_update=True
    )
    request_payload = {**command.model_dump(mode="json"), "fault_code": fault_code}
    existing_command = await _existing_simulation_command(
        session, ecu=locked, command_id=command.command_id
    )
    if existing_command is not None:
        if existing_command.kind == "fault_clear" and existing_command.request == request_payload:
            return existing_command, True
        raise EcuSimulationCommandConflictError()
    if command.expected_version != locked.version:
        raise EcuStateVersionConflictError(current_version=locked.version)
    faults = [EcuFault.model_validate(item) for item in locked.faults]
    current = next((item for item in faults if item.code == fault_code), None)
    if current is None:
        raise EcuFaultContractError(reason="cannot clear an unknown fault")
    if current.status is EcuFaultStatus.HEALED:
        raise EcuFaultContractError(reason="fault is already healed")
    now_ms = locked.simulation_time_ms
    current = current.model_copy(
        update={
            "status": EcuFaultStatus.HEALED,
            "active": False,
            "latched": False,
            "healed_at_ms": now_ms,
        }
    )
    faults = [current if item.code == fault_code else item for item in faults]
    previous_version = locked.version
    locked.faults = [item.model_dump(mode="json") for item in faults]
    _apply_fault_operational_state(locked, faults)
    locked.version += 1
    result = {"transition": "cleared", "fault": current.model_dump(mode="json")}
    execution = EcuSimulationCommand(
        ecu_id=locked.id,
        command_id=command.command_id,
        kind="fault_clear",
        request=request_payload,
        result=result,
        previous_version=previous_version,
        state_version=locked.version,
        previous_time_ms=now_ms,
        simulation_time_ms=now_ms,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    _record_fault_evidence(
        session,
        execution=execution,
        ecu=locked,
        vehicle=vehicle,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
    )
    return execution, False


def dtc_candidates(ecu: ElectronicControlUnit) -> list[EcuDtcCandidate]:
    return [
        EcuDtcCandidate(
            source_fault_code=fault.code,
            severity=fault.severity,
            status=fault.status,
            test_failed=fault.active,
            pending_dtc=fault.status in {EcuFaultStatus.PENDING, EcuFaultStatus.CONFIRMED},
            confirmed_dtc=fault.status is EcuFaultStatus.CONFIRMED,
            warning_indicator_requested=(
                fault.active and fault.severity is EcuFaultSeverity.CRITICAL
            ),
            occurrence_count=fault.occurrence_count,
            first_seen_ms=fault.first_seen_ms,
            last_seen_ms=fault.last_seen_ms,
            confirmed_at_ms=fault.confirmed_at_ms,
        )
        for fault in sorted(
            (EcuFault.model_validate(item) for item in ecu.faults), key=lambda item: item.code
        )
    ]


async def publish_ecu_signal(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    signal_name: str,
    command: EcuSignalPublishCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[EcuSimulationCommand, bool]:
    locked = await require_ecu(
        session, vehicle=vehicle, identifier=ecu.identifier, for_update=True
    )
    request_payload = {**command.model_dump(mode="json"), "signal_name": signal_name}
    existing = await _existing_simulation_command(
        session, ecu=locked, command_id=command.command_id
    )
    if existing is not None:
        if existing.kind == "signal_publish" and existing.request == request_payload:
            return existing, True
        raise EcuSimulationCommandConflictError()
    if command.expected_version != locked.version:
        raise EcuStateVersionConflictError(current_version=locked.version)
    signals = [EcuSignalContract.model_validate(item) for item in (locked.signals or [])]
    current = next(
        (
            item
            for item in signals
            if item.direction is EcuSignalDirection.PRODUCED and item.name == signal_name
        ),
        None,
    )
    if current is None:
        raise EcuSignalContractError(reason="unknown produced signal")
    updated = _signal_with_value(current, value=command.value, time_ms=locked.simulation_time_ms)
    signals = [
        updated
        if item.direction is EcuSignalDirection.PRODUCED and item.name == signal_name
        else item
        for item in signals
    ]
    previous_version = locked.version
    locked.signals = [item.model_dump(mode="json") for item in signals]
    locked.version += 1
    result = {"signal": updated.model_dump(mode="json")}
    execution = EcuSimulationCommand(
        ecu_id=locked.id,
        command_id=command.command_id,
        kind="signal_publish",
        request=request_payload,
        result=result,
        previous_version=previous_version,
        state_version=locked.version,
        previous_time_ms=locked.simulation_time_ms,
        simulation_time_ms=locked.simulation_time_ms,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    evidence = {
        **_simulation_evidence(execution, locked, vehicle),
        "signal_name": updated.name,
        "direction": updated.direction.value,
        "data_type": updated.data_type.value,
        "updated_at_ms": updated.updated_at_ms,
    }
    enqueue_event(
        session,
        event_type="atep.ecu.signal.published.v1",
        aggregate_type="ecu",
        aggregate_id=locked.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.signal_published",
        resource_type="ecu",
        resource_id=locked.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return execution, False


async def create_signal_route(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    gateway: ElectronicControlUnit,
    command: EcuSignalRouteCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> EcuSignalRoute:
    if gateway.ecu_type != EcuType.GATEWAY.value:
        raise EcuSignalContractError(reason="signal routes must be owned by a gateway ECU")
    if command.source_ecu_id == command.target_ecu_id:
        raise EcuSignalContractError(reason="source and target ECUs must differ")
    existing = await session.scalar(
        select(EcuSignalRoute).where(
            EcuSignalRoute.gateway_ecu_id == gateway.id,
            EcuSignalRoute.identifier == command.identifier,
        )
    )
    if existing is not None:
        raise DuplicateEcuSignalRouteError()
    source = await require_ecu(session, vehicle=vehicle, identifier=command.source_ecu_id)
    target = await require_ecu(session, vehicle=vehicle, identifier=command.target_ecu_id)
    source_signal = _require_signal(
        source, name=command.source_signal, direction=EcuSignalDirection.PRODUCED
    )
    target_signal = _require_signal(
        target, name=command.target_signal, direction=EcuSignalDirection.CONSUMED
    )
    if source_signal.data_type is not target_signal.data_type:
        raise EcuSignalContractError(reason="route signal data types must match")
    if source_signal.unit != target_signal.unit:
        raise EcuSignalContractError(reason="route signal units must match")
    route = EcuSignalRoute(
        gateway_ecu_id=gateway.id,
        identifier=command.identifier,
        source_ecu_id=source.id,
        source_signal=source_signal.name,
        target_ecu_id=target.id,
        target_signal=target_signal.name,
        enabled=command.enabled,
    )
    try:
        async with session.begin_nested():
            session.add(route)
            await session.flush()
    except IntegrityError as exc:
        raise DuplicateEcuSignalRouteError() from exc
    evidence = {
        **_ecu_evidence(gateway, vehicle),
        "route_id": str(route.id),
        "route_identifier": route.identifier,
        "source_ecu_id": source.identifier,
        "source_signal": route.source_signal,
        "target_ecu_id": target.identifier,
        "target_signal": route.target_signal,
        "enabled": route.enabled,
    }
    enqueue_event(
        session,
        event_type="atep.ecu.signal.route.created.v1",
        aggregate_type="ecu_signal_route",
        aggregate_id=route.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.signal_route_created",
        resource_type="ecu_signal_route",
        resource_id=route.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return route


async def list_signal_routes(
    session: AsyncSession, *, gateway: ElectronicControlUnit, limit: int, offset: int
) -> tuple[list[EcuSignalRoute], int]:
    query = select(EcuSignalRoute).where(EcuSignalRoute.gateway_ecu_id == gateway.id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(EcuSignalRoute.identifier).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def require_signal_route(
    session: AsyncSession, *, gateway: ElectronicControlUnit, route_id: UUID
) -> EcuSignalRoute:
    route = await session.scalar(
        select(EcuSignalRoute).where(
            EcuSignalRoute.gateway_ecu_id == gateway.id, EcuSignalRoute.id == route_id
        )
    )
    if route is None:
        raise ResourceNotFoundError("ecu signal route")
    return route


async def transfer_signal_route(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    gateway: ElectronicControlUnit,
    route: EcuSignalRoute,
    command: EcuSignalRouteTransferCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[EcuSimulationCommand, bool, ElectronicControlUnit, ElectronicControlUnit]:
    if not route.enabled:
        raise EcuSignalContractError(reason="signal route is disabled")
    source = await session.scalar(
        select(ElectronicControlUnit)
        .where(ElectronicControlUnit.id == route.source_ecu_id)
        .with_for_update()
    )
    target = await session.scalar(
        select(ElectronicControlUnit)
        .where(ElectronicControlUnit.id == route.target_ecu_id)
        .with_for_update()
    )
    if source is None or target is None:
        raise ResourceNotFoundError("route ECU")
    request_payload = {
        **command.model_dump(mode="json"),
        "route_id": str(route.id),
        "gateway_ecu_id": gateway.identifier,
    }
    existing = await _existing_simulation_command(
        session, ecu=target, command_id=command.command_id
    )
    if existing is not None:
        if existing.kind == "signal_route_transfer" and existing.request == request_payload:
            return existing, True, source, target
        raise EcuSimulationCommandConflictError()
    if command.expected_source_version != source.version:
        raise EcuStateVersionConflictError(current_version=source.version)
    if command.expected_target_version != target.version:
        raise EcuStateVersionConflictError(current_version=target.version)
    source_signal = _require_signal(
        source, name=route.source_signal, direction=EcuSignalDirection.PRODUCED
    )
    target_signal = _require_signal(
        target, name=route.target_signal, direction=EcuSignalDirection.CONSUMED
    )
    updated_target = _signal_with_value(
        target_signal, value=source_signal.value, time_ms=target.simulation_time_ms
    )
    target_signals = [EcuSignalContract.model_validate(item) for item in (target.signals or [])]
    target.signals = []
    for item in target_signals:
        is_target = (
            item.direction is EcuSignalDirection.CONSUMED
            and item.name == route.target_signal
        )
        target.signals.append(
            (updated_target if is_target else item).model_dump(mode="json")
        )
    previous_target_version = target.version
    target.version += 1
    result = {
        "route_id": str(route.id),
        "gateway_ecu_id": gateway.identifier,
        "source_ecu_id": source.identifier,
        "target_ecu_id": target.identifier,
        "source_signal": source_signal.model_dump(mode="json"),
        "target_signal": updated_target.model_dump(mode="json"),
    }
    execution = EcuSimulationCommand(
        ecu_id=target.id,
        command_id=command.command_id,
        kind="signal_route_transfer",
        request=request_payload,
        result=result,
        previous_version=previous_target_version,
        state_version=target.version,
        previous_time_ms=target.simulation_time_ms,
        simulation_time_ms=target.simulation_time_ms,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    evidence = {
        "command_id": execution.command_id,
        "vehicle_id": vehicle.identifier,
        "gateway_ecu_id": gateway.identifier,
        "route_id": str(route.id),
        "source_ecu_id": source.identifier,
        "source_signal": source_signal.name,
        "source_version": source.version,
        "target_ecu_id": target.identifier,
        "target_signal": updated_target.name,
        "previous_target_version": previous_target_version,
        "target_version": target.version,
    }
    enqueue_event(
        session,
        event_type="atep.ecu.signal.routed.v1",
        aggregate_type="ecu_signal_route",
        aggregate_id=route.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.signal_routed",
        resource_type="ecu_signal_route",
        resource_id=route.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return execution, False, source, target


def _require_signal(
    ecu: ElectronicControlUnit, *, name: str, direction: EcuSignalDirection
) -> EcuSignalContract:
    signal = next(
        (
            EcuSignalContract.model_validate(item)
            for item in (ecu.signals or [])
            if item.get("name") == name and item.get("direction") == direction.value
        ),
        None,
    )
    if signal is None:
        raise EcuSignalContractError(reason=f"unknown {direction.value} signal: {name}")
    return signal


def _signal_with_value(
    signal: EcuSignalContract, *, value: bool | int | float, time_ms: int
) -> EcuSignalContract:
    try:
        return EcuSignalContract.model_validate(
            {**signal.model_dump(mode="json"), "value": value, "updated_at_ms": time_ms}
        )
    except ValidationError as exc:
        reason = exc.errors()[0]["msg"] if exc.errors() else "invalid signal value"
        raise EcuSignalContractError(reason=str(reason)) from exc


def _apply_fault_operational_state(
    ecu: ElectronicControlUnit, faults: list[EcuFault]
) -> None:
    critical = any(
        fault.active
        and fault.severity is EcuFaultSeverity.CRITICAL
        and fault.status is EcuFaultStatus.CONFIRMED
        for fault in faults
    )
    if critical:
        ecu.operational_state = EcuOperationalState.FAULT.value
    elif ecu.operational_state == EcuOperationalState.FAULT.value:
        ecu.operational_state = EcuOperationalState.DEGRADED.value


def _record_fault_evidence(
    session: AsyncSession,
    *,
    execution: EcuSimulationCommand,
    ecu: ElectronicControlUnit,
    vehicle: Vehicle,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> None:
    evidence = {
        **_simulation_evidence(execution, ecu, vehicle),
        "fault_code": execution.result["fault"]["code"],
        "transition": execution.result["transition"],
        "status": execution.result["fault"]["status"],
        "active": execution.result["fault"]["active"],
        "occurrence_count": execution.result["fault"]["occurrence_count"],
        "healing_count": execution.result["fault"]["healing_count"],
    }
    enqueue_event(
        session,
        event_type="atep.ecu.fault.lifecycle.changed.v1",
        aggregate_type="ecu",
        aggregate_id=ecu.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.fault_lifecycle_changed",
        resource_type="ecu",
        resource_id=ecu.id,
        correlation_id=correlation_id,
        details=evidence,
    )


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
        "profile_version": ecu.profile_version,
    }


def _profile_state(
    state: EcuStatePayload, *, ecu_type: EcuType, use_profile_defaults: bool
) -> EcuStatePayload:
    profile = behavior_profile(ecu_type)
    tasks = list(profile.tasks) if use_profile_defaults else state.cyclic_tasks
    supported = {task.task_id: task for task in profile.tasks}
    for task in tasks:
        expected = supported.get(task.task_id)
        if expected is None:
            raise EcuProfileContractError(reason=f"unsupported task: {task.task_id}")
        if task.period_ms != expected.period_ms or task.offset_ms != expected.offset_ms:
            raise EcuProfileContractError(
                reason=f"task schedule differs from profile: {task.task_id}"
            )
    unknown_state = set(state.behavior_state) - set(profile.initial_state)
    if unknown_state:
        raise EcuProfileContractError(
            reason=f"unsupported behavior state: {sorted(unknown_state)[0]}"
        )
    behavior_state = dict(profile.initial_state)
    behavior_state.update(state.behavior_state)
    return state.model_copy(update={"cyclic_tasks": tasks, "behavior_state": behavior_state})


def _memory_state(
    state: EcuStatePayload, *, use_default_region: bool
) -> EcuStatePayload:
    regions = state.memory_regions
    if use_default_region:
        regions = [
            EcuMemoryRegion(
                name="legacy_nvm",
                kind=EcuMemoryRegionKind.NON_VOLATILE,
                start_address=0,
                size=65_536,
            )
        ]
    return EcuStatePayload.model_validate(
        {**state.model_dump(mode="json"), "memory_regions": regions}
    )
