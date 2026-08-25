from math import ceil
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.can_network.error_state import node_error_state, set_node_error_state
from atep.can_network.models import CanFaultExecution, CanNetwork
from atep.can_network.schemas import CanBusRecoveryCommand, CanFaultInjectionCommand, CanFaultType
from atep.can_network.service import _contract, require_can_network
from atep.core.errors import (
    CanFaultCommandConflictError,
    CanFaultStateError,
    CanNetworkContractError,
    CanNetworkVersionConflictError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


def _duration_us(bits: int, bitrate_kbps: int) -> int:
    return ceil((bits * 1000) / bitrate_kbps)


async def _existing(
    session: AsyncSession, network: CanNetwork, command_id: str, request: dict[str, Any]
) -> CanFaultExecution | None:
    item = await session.scalar(
        select(CanFaultExecution).where(
            CanFaultExecution.network_id == network.id,
            CanFaultExecution.command_id == command_id,
        )
    )
    if item is not None and item.request != request:
        raise CanFaultCommandConflictError()
    return item


async def inject_fault(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: CanFaultInjectionCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[CanFaultExecution, CanNetwork, bool]:
    network = await require_can_network(session, vehicle=vehicle, for_update=True)
    request = command.model_dump(mode="json")
    if item := await _existing(session, network, command.command_id, request):
        return item, network, True
    if command.expected_version != network.version:
        raise CanNetworkVersionConflictError(current_version=network.version)
    contract = _contract(network, command.contract_id)
    if command.fault_type is CanFaultType.TRANSMISSION_ERROR:
        if command.target_node_id != contract.producer_node_id:
            raise CanNetworkContractError(
                reason="a transmission fault must target the declared producer"
            )
    elif command.target_node_id not in contract.consumer_node_ids:
        raise CanNetworkContractError(
            reason="a reception fault or frame loss must target a declared consumer"
        )

    before = node_error_state(network, command.target_node_id)
    tec, rec = before.transmit_error_count, before.receive_error_count
    error_frames = 0
    lost_frames = 0
    if command.fault_type is CanFaultType.TRANSMISSION_ERROR:
        tec += 8 * command.occurrences
        error_frames = command.occurrences
    elif command.fault_type is CanFaultType.RECEPTION_ERROR:
        rec += command.occurrences
        error_frames = command.occurrences
    else:
        lost_frames = command.occurrences
    after = set_node_error_state(network, command.target_node_id, tec=tec, rec=rec)
    elapsed = command.advance_time_us + _duration_us(14 * error_frames, network.bitrate_kbps)
    previous_version = network.version
    network.version += 1
    network.simulation_time_us += elapsed
    result: dict[str, Any] = {
        "fault_type": command.fault_type.value,
        "contract_id": contract.identifier,
        "occurrences": command.occurrences,
        "error_frames": error_frames,
        "lost_frames": lost_frames,
        "elapsed_us": elapsed,
        "before": before.model_dump(mode="json"),
        "after": after.model_dump(mode="json"),
    }
    execution = CanFaultExecution(
        network_id=network.id,
        command_id=command.command_id,
        operation="inject",
        target_node_id=command.target_node_id,
        request=request,
        result=result,
        previous_version=previous_version,
        network_version=network.version,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    evidence = {
        "vehicle_id": vehicle.identifier,
        "network_id": network.identifier,
        "command_id": command.command_id,
        "target_node_id": str(command.target_node_id),
        "fault_type": command.fault_type.value,
        "error_state": after.state.value,
        "error_frames": error_frames,
        "lost_frames": lost_frames,
        "previous_version": previous_version,
        "network_version": network.version,
    }
    enqueue_event(
        session,
        event_type="atep.can.fault.injected.v1",
        aggregate_type="can_network",
        aggregate_id=network.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="can.fault_injected",
        resource_type="can_network",
        resource_id=network.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return execution, network, False


async def recover_node(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: CanBusRecoveryCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[CanFaultExecution, CanNetwork, bool]:
    network = await require_can_network(session, vehicle=vehicle, for_update=True)
    request = command.model_dump(mode="json")
    if item := await _existing(session, network, command.command_id, request):
        return item, network, True
    if command.expected_version != network.version:
        raise CanNetworkVersionConflictError(current_version=network.version)
    before = node_error_state(network, command.target_node_id)
    if before.state.value != "bus_off":
        raise CanFaultStateError(reason="only a bus-off node can be recovered")
    after = set_node_error_state(network, command.target_node_id, tec=0, rec=0)
    elapsed = _duration_us(command.recessive_sequences * 11, network.bitrate_kbps)
    previous_version = network.version
    network.version += 1
    network.simulation_time_us += elapsed
    result: dict[str, Any] = {
        "recessive_sequences": command.recessive_sequences,
        "elapsed_us": elapsed,
        "before": before.model_dump(mode="json"),
        "after": after.model_dump(mode="json"),
    }
    execution = CanFaultExecution(
        network_id=network.id,
        command_id=command.command_id,
        operation="recover",
        target_node_id=command.target_node_id,
        request=request,
        result=result,
        previous_version=previous_version,
        network_version=network.version,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    evidence = {
        "vehicle_id": vehicle.identifier,
        "network_id": network.identifier,
        "command_id": command.command_id,
        "target_node_id": str(command.target_node_id),
        "recessive_sequences": command.recessive_sequences,
        "elapsed_us": elapsed,
        "previous_version": previous_version,
        "network_version": network.version,
    }
    enqueue_event(
        session,
        event_type="atep.can.bus.recovered.v1",
        aggregate_type="can_network",
        aggregate_id=network.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="can.bus_recovered",
        resource_type="can_network",
        resource_id=network.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return execution, network, False


async def list_fault_executions(
    session: AsyncSession, *, network: CanNetwork, limit: int, offset: int
) -> tuple[list[CanFaultExecution], int]:
    query = select(CanFaultExecution).where(CanFaultExecution.network_id == network.id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(CanFaultExecution.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total or 0)


async def require_fault_execution(
    session: AsyncSession, *, network: CanNetwork, command_id: str
) -> CanFaultExecution:
    item = await session.scalar(
        select(CanFaultExecution).where(
            CanFaultExecution.network_id == network.id, CanFaultExecution.command_id == command_id
        )
    )
    if item is None:
        raise ResourceNotFoundError("can_fault_execution")
    return item
