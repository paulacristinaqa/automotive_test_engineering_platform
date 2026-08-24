from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.can_network.models import CanFrameTransmission, CanNetwork
from atep.can_network.schemas import CanFrameContract, CanFrameSubmitCommand, CanNetworkCreate
from atep.core.errors import (
    CanFrameCommandConflictError,
    CanNetworkAlreadyExistsError,
    CanNetworkContractError,
    CanNetworkVersionConflictError,
    ResourceNotFoundError,
)
from atep.ecus.models import ElectronicControlUnit
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


async def create_can_network(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: CanNetworkCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> CanNetwork:
    if await session.scalar(select(CanNetwork).where(CanNetwork.vehicle_id == vehicle.id)):
        raise CanNetworkAlreadyExistsError()
    declared = {item.ecu_id for item in command.nodes}
    result = await session.execute(
        select(ElectronicControlUnit.id).where(
            ElectronicControlUnit.vehicle_id == vehicle.id,
            ElectronicControlUnit.id.in_(declared),
        )
    )
    if set(result.scalars().all()) != declared:
        raise CanNetworkContractError(reason="every CAN node must reference an ECU in the vehicle")
    network = CanNetwork(
        vehicle_id=vehicle.id,
        identifier=command.identifier,
        display_name=command.display_name.strip(),
        bitrate_kbps=command.bitrate_kbps,
        can_fd_enabled=command.can_fd_enabled,
        data_bitrate_kbps=command.data_bitrate_kbps,
        nodes=[item.model_dump(mode="json") for item in command.nodes],
        frame_contracts=[item.model_dump(mode="json") for item in command.frame_contracts],
        version=1,
        simulation_time_us=0,
        next_sequence=1,
    )
    try:
        async with session.begin_nested():
            session.add(network)
            await session.flush()
    except IntegrityError as exc:
        raise CanNetworkAlreadyExistsError() from exc
    evidence = {
        "vehicle_id": vehicle.identifier,
        "network_id": network.identifier,
        "node_count": len(network.nodes),
        "frame_contract_count": len(network.frame_contracts),
        "bitrate_kbps": network.bitrate_kbps,
        "can_fd_enabled": network.can_fd_enabled,
        "data_bitrate_kbps": network.data_bitrate_kbps,
        "version": network.version,
    }
    enqueue_event(
        session,
        event_type="atep.can.network.created.v1",
        aggregate_type="can_network",
        aggregate_id=network.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="can.network_created",
        resource_type="can_network",
        resource_id=network.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return network


async def require_can_network(
    session: AsyncSession, *, vehicle: Vehicle, for_update: bool = False
) -> CanNetwork:
    query = select(CanNetwork).where(CanNetwork.vehicle_id == vehicle.id)
    if for_update:
        query = query.with_for_update()
    network = await session.scalar(query)
    if network is None:
        raise ResourceNotFoundError("can_network")
    return network


def _contract(network: CanNetwork, identifier: str) -> CanFrameContract:
    for item in network.frame_contracts:
        contract = CanFrameContract.model_validate(item)
        if contract.identifier == identifier:
            return contract
    raise CanNetworkContractError(reason="frame contract does not exist")


async def submit_can_frame(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: CanFrameSubmitCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[CanFrameTransmission, CanNetwork, bool]:
    network = await require_can_network(session, vehicle=vehicle, for_update=True)
    request_payload = command.model_dump(mode="json")
    existing = await session.scalar(
        select(CanFrameTransmission).where(
            CanFrameTransmission.network_id == network.id,
            CanFrameTransmission.command_id == command.command_id,
        )
    )
    if existing is not None:
        if existing.request == request_payload:
            return existing, network, True
        raise CanFrameCommandConflictError()
    if command.expected_version != network.version:
        raise CanNetworkVersionConflictError(current_version=network.version)
    contract = _contract(network, command.contract_id)
    if command.producer_node_id != contract.producer_node_id:
        raise CanNetworkContractError(reason="only the declared producer may submit this frame")
    if len(command.payload) != contract.dlc:
        raise CanNetworkContractError(reason="payload length must equal the frame contract DLC")
    previous_version = network.version
    transmission_time = network.simulation_time_us + command.advance_time_us
    transmission = CanFrameTransmission(
        network_id=network.id,
        command_id=command.command_id,
        contract_id=contract.identifier,
        producer_node_id=command.producer_node_id,
        frame_id=contract.frame_id,
        frame_format=contract.frame_format.value,
        protocol=contract.protocol.value,
        bitrate_switch=contract.bitrate_switch,
        request=request_payload,
        payload=list(command.payload),
        sequence=network.next_sequence,
        transmission_time_us=transmission_time,
        previous_version=previous_version,
        network_version=previous_version + 1,
        requested_by_user_id=actor_user_id,
    )
    network.simulation_time_us = transmission_time
    network.next_sequence += 1
    network.version += 1
    session.add(transmission)
    await session.flush()
    evidence = {
        "vehicle_id": vehicle.identifier,
        "network_id": network.identifier,
        "contract_id": contract.identifier,
        "frame_id": contract.frame_id,
        "frame_format": contract.frame_format.value,
        "protocol": contract.protocol.value,
        "bitrate_switch": contract.bitrate_switch,
        "dlc": contract.dlc,
        "sequence": transmission.sequence,
        "transmission_time_us": transmission.transmission_time_us,
        "previous_version": previous_version,
        "network_version": network.version,
    }
    enqueue_event(
        session,
        event_type="atep.can.frame.submitted.v1",
        aggregate_type="can_network",
        aggregate_id=network.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="can.frame_submitted",
        resource_type="can_network",
        resource_id=network.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return transmission, network, False


async def list_transmissions(
    session: AsyncSession, *, network: CanNetwork, limit: int, offset: int
) -> tuple[list[CanFrameTransmission], int]:
    query = select(CanFrameTransmission).where(CanFrameTransmission.network_id == network.id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(CanFrameTransmission.sequence.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)
