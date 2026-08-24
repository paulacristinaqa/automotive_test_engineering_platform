from dataclasses import dataclass
from math import ceil
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.can_network.models import (
    CanArbitrationExecution,
    CanFrameTransmission,
    CanNetwork,
)
from atep.can_network.schemas import (
    CanArbitratedFrame,
    CanArbitrationCommand,
    CanArbitrationResponse,
    CanBusUtilization,
    CanDeliveryEvidence,
    CanFrameContract,
    CanFrameFormat,
    CanFrameProtocol,
)
from atep.can_network.service import _contract, require_can_network
from atep.core.errors import (
    CanArbitrationCommandConflictError,
    CanNetworkContractError,
    CanNetworkVersionConflictError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


@dataclass(frozen=True)
class _ResolvedContender:
    contract: CanFrameContract
    producer_node_id: UUID
    payload: list[int]
    ready_at_us: int


@dataclass(frozen=True)
class _FrameTiming:
    bit_count: int
    nominal_bit_count: int
    data_bit_count: int
    nominal_phase_duration_us: int
    data_phase_duration_us: int

    @property
    def duration_us(self) -> int:
        return self.nominal_phase_duration_us + self.data_phase_duration_us


def _duration_us(bit_count: int, bitrate_kbps: int) -> int:
    return ceil((bit_count * 1000) / bitrate_kbps)


def frame_timing(contract: CanFrameContract, network: CanNetwork) -> _FrameTiming:
    """Return a deterministic, stuffing-free classic CAN/CAN FD timing model."""
    if contract.protocol is CanFrameProtocol.CLASSIC:
        bit_count = (47 if contract.frame_format is CanFrameFormat.STANDARD else 67) + (
            8 * contract.dlc
        )
        return _FrameTiming(
            bit_count=bit_count,
            nominal_bit_count=bit_count,
            data_bit_count=0,
            nominal_phase_duration_us=_duration_us(bit_count, network.bitrate_kbps),
            data_phase_duration_us=0,
        )

    nominal_bit_count = 32 if contract.frame_format is CanFrameFormat.STANDARD else 52
    crc_bits = 17 if contract.dlc <= 16 else 21
    data_bit_count = (8 * contract.dlc) + crc_bits
    data_bitrate = (
        network.data_bitrate_kbps
        if contract.bitrate_switch and network.data_bitrate_kbps is not None
        else network.bitrate_kbps
    )
    return _FrameTiming(
        bit_count=nominal_bit_count + data_bit_count,
        nominal_bit_count=nominal_bit_count,
        data_bit_count=data_bit_count,
        nominal_phase_duration_us=_duration_us(nominal_bit_count, network.bitrate_kbps),
        data_phase_duration_us=_duration_us(data_bit_count, data_bitrate),
    )


def _resolve_contenders(
    network: CanNetwork, command: CanArbitrationCommand
) -> list[_ResolvedContender]:
    resolved: list[_ResolvedContender] = []
    for contender in command.contenders:
        contract = _contract(network, contender.contract_id)
        if contender.producer_node_id != contract.producer_node_id:
            raise CanNetworkContractError(
                reason="only the declared producer may contend for a frame"
            )
        if len(contender.payload) != contract.dlc:
            raise CanNetworkContractError(reason="payload length must equal the frame contract DLC")
        resolved.append(
            _ResolvedContender(
                contract=contract,
                producer_node_id=contender.producer_node_id,
                payload=contender.payload,
                ready_at_us=network.simulation_time_us + contender.ready_offset_us,
            )
        )
    return resolved


def _arbitrate(
    network: CanNetwork, contenders: list[_ResolvedContender]
) -> tuple[list[CanArbitratedFrame], CanBusUtilization]:
    pending = list(contenders)
    clock = network.simulation_time_us
    occupied_us = 0
    frames: list[CanArbitratedFrame] = []
    while pending:
        ready = [item for item in pending if item.ready_at_us <= clock]
        if not ready:
            clock = min(item.ready_at_us for item in pending)
            ready = [item for item in pending if item.ready_at_us <= clock]
        winner = min(
            ready,
            key=lambda item: (
                item.contract.frame_id,
                item.contract.frame_format is CanFrameFormat.EXTENDED,
                item.contract.identifier,
            ),
        )
        pending.remove(winner)
        timing = frame_timing(winner.contract, network)
        bit_count = timing.bit_count
        duration_us = timing.duration_us
        started_at_us = clock
        clock += duration_us
        occupied_us += duration_us
        latency_us = clock - winner.ready_at_us
        frames.append(
            CanArbitratedFrame(
                rank=len(frames) + 1,
                sequence=network.next_sequence + len(frames),
                contract_id=winner.contract.identifier,
                frame_id=winner.contract.frame_id,
                frame_format=winner.contract.frame_format,
                protocol=winner.contract.protocol,
                bitrate_switch=winner.contract.bitrate_switch,
                producer_node_id=winner.producer_node_id,
                dlc=winner.contract.dlc,
                bit_count=bit_count,
                nominal_bit_count=timing.nominal_bit_count,
                data_bit_count=timing.data_bit_count,
                nominal_phase_duration_us=timing.nominal_phase_duration_us,
                data_phase_duration_us=timing.data_phase_duration_us,
                ready_at_us=winner.ready_at_us,
                started_at_us=started_at_us,
                completed_at_us=clock,
                duration_us=duration_us,
                deliveries=[
                    CanDeliveryEvidence(
                        consumer_node_id=consumer,
                        received_at_us=clock,
                        latency_us=latency_us,
                    )
                    for consumer in winner.contract.consumer_node_ids
                ],
            )
        )
    window_duration_us = clock - network.simulation_time_us
    idle_us = window_duration_us - occupied_us
    utilization = CanBusUtilization(
        window_start_us=network.simulation_time_us,
        window_end_us=clock,
        window_duration_us=window_duration_us,
        occupied_us=occupied_us,
        idle_us=idle_us,
        utilization_percent=round((occupied_us / window_duration_us) * 100, 4),
        maximum_latency_us=max(frame.completed_at_us - frame.ready_at_us for frame in frames),
    )
    return frames, utilization


def arbitration_response(
    execution: CanArbitrationExecution,
    network: CanNetwork,
    vehicle: Vehicle,
    *,
    duplicate: bool = False,
) -> CanArbitrationResponse:
    result = execution.result
    return CanArbitrationResponse(
        command_id=execution.command_id,
        vehicle_id=vehicle.identifier,
        network_id=network.identifier,
        previous_version=execution.previous_version,
        network_version=execution.network_version,
        frames=result["frames"],
        utilization=result["utilization"],
        duplicate=duplicate,
        created_at=execution.created_at,
    )


async def execute_arbitration(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: CanArbitrationCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[CanArbitrationExecution, CanNetwork, bool]:
    network = await require_can_network(session, vehicle=vehicle, for_update=True)
    request_payload = command.model_dump(mode="json")
    existing = await session.scalar(
        select(CanArbitrationExecution).where(
            CanArbitrationExecution.network_id == network.id,
            CanArbitrationExecution.command_id == command.command_id,
        )
    )
    if existing is not None:
        if existing.request == request_payload:
            return existing, network, True
        raise CanArbitrationCommandConflictError()
    if command.expected_version != network.version:
        raise CanNetworkVersionConflictError(current_version=network.version)

    contenders = _resolve_contenders(network, command)
    frames, utilization = _arbitrate(network, contenders)
    previous_version = network.version
    network.version += 1
    network.next_sequence += len(frames)
    network.simulation_time_us = utilization.window_end_us
    result: dict[str, Any] = {
        "frames": [frame.model_dump(mode="json") for frame in frames],
        "utilization": utilization.model_dump(mode="json"),
    }
    execution = CanArbitrationExecution(
        network_id=network.id,
        command_id=command.command_id,
        request=request_payload,
        result=result,
        contender_count=len(contenders),
        previous_version=previous_version,
        network_version=network.version,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    ordered_contenders = sorted(contenders, key=lambda item: frame_order(frames, item))
    for frame, contender in zip(frames, ordered_contenders, strict=True):
        session.add(
            CanFrameTransmission(
                network_id=network.id,
                command_id=f"arb:{command.command_id}:{frame.rank}",
                contract_id=frame.contract_id,
                producer_node_id=frame.producer_node_id,
                frame_id=frame.frame_id,
                frame_format=frame.frame_format.value,
                protocol=frame.protocol.value,
                bitrate_switch=frame.bitrate_switch,
                request={
                    "arbitration_command_id": command.command_id,
                    "ready_at_us": frame.ready_at_us,
                },
                payload=contender.payload,
                sequence=frame.sequence,
                transmission_time_us=frame.completed_at_us,
                previous_version=previous_version,
                network_version=network.version,
                requested_by_user_id=actor_user_id,
            )
        )
    await session.flush()
    evidence = {
        "vehicle_id": vehicle.identifier,
        "network_id": network.identifier,
        "command_id": command.command_id,
        "contender_count": len(contenders),
        "window_duration_us": utilization.window_duration_us,
        "occupied_us": utilization.occupied_us,
        "utilization_percent": utilization.utilization_percent,
        "maximum_latency_us": utilization.maximum_latency_us,
        "fd_frame_count": sum(
            frame.protocol is CanFrameProtocol.FD for frame in frames
        ),
        "bitrate_switched_frame_count": sum(frame.bitrate_switch for frame in frames),
        "previous_version": previous_version,
        "network_version": network.version,
    }
    enqueue_event(
        session,
        event_type="atep.can.arbitration.completed.v1",
        aggregate_type="can_network",
        aggregate_id=network.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="can.arbitration_executed",
        resource_type="can_network",
        resource_id=network.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return execution, network, False


def frame_order(frames: list[CanArbitratedFrame], contender: _ResolvedContender) -> int:
    return next(
        frame.rank for frame in frames if frame.contract_id == contender.contract.identifier
    )


async def list_arbitrations(
    session: AsyncSession, *, network: CanNetwork, limit: int, offset: int
) -> tuple[list[CanArbitrationExecution], int]:
    query = select(CanArbitrationExecution).where(CanArbitrationExecution.network_id == network.id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(CanArbitrationExecution.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def require_arbitration(
    session: AsyncSession, *, network: CanNetwork, command_id: str
) -> CanArbitrationExecution:
    execution = await session.scalar(
        select(CanArbitrationExecution).where(
            CanArbitrationExecution.network_id == network.id,
            CanArbitrationExecution.command_id == command_id,
        )
    )
    if execution is None:
        raise ResourceNotFoundError("can_arbitration")
    return execution
