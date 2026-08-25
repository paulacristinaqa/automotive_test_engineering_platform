from math import ceil
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.can_network.arbitration_service import frame_timing
from atep.can_network.models import CanNetwork, MultiBusGatewayExecution
from atep.can_network.schemas import (
    EthernetMessageContract,
    GatewayRouteCommand,
    GatewayRouteContract,
    LinFrameContract,
    MultiBusConfigurationCommand,
    VehicleBusProtocol,
)
from atep.can_network.service import _contract, require_can_network
from atep.core.errors import (
    CanNetworkVersionConflictError,
    MultiBusGatewayCommandConflictError,
    MultiBusGatewayContractError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


def _node_roles(network: CanNetwork) -> dict[UUID, str]:
    return {UUID(item["ecu_id"]): str(item["role"]) for item in network.nodes}


def _lin_contracts(
    command: MultiBusConfigurationCommand,
) -> dict[str, tuple[LinFrameContract, int]]:
    return {
        frame.identifier: (frame, channel.bitrate_kbps)
        for channel in command.lin_channels
        for frame in channel.frames
    }


def _ethernet_contracts(
    command: MultiBusConfigurationCommand,
) -> dict[str, tuple[EthernetMessageContract, int]]:
    return {
        message.identifier: (message, segment.speed_mbps)
        for segment in command.ethernet_segments
        for message in segment.messages
    }


def _validate_configuration(network: CanNetwork, command: MultiBusConfigurationCommand) -> None:
    roles = _node_roles(network)
    known = set(roles)
    lin = _lin_contracts(command)
    ethernet = _ethernet_contracts(command)
    lin_ids = [frame.identifier for channel in command.lin_channels for frame in channel.frames]
    ethernet_ids = [
        message.identifier for segment in command.ethernet_segments for message in segment.messages
    ]
    if len(lin_ids) != len(set(lin_ids)) or len(ethernet_ids) != len(set(ethernet_ids)):
        raise MultiBusGatewayContractError(reason="transport contract identifiers must be unique")
    for channel in command.lin_channels:
        referenced = {channel.master_node_id}
        for frame in channel.frames:
            referenced.add(frame.publisher_node_id)
            referenced.update(frame.subscriber_node_ids)
        if not referenced <= known:
            raise MultiBusGatewayContractError(reason="LIN contracts may reference only CAN nodes")
    for segment in command.ethernet_segments:
        ethernet_referenced: set[UUID] = set()
        for message in segment.messages:
            ethernet_referenced.add(message.source_node_id)
            ethernet_referenced.update(message.destination_node_ids)
        if not ethernet_referenced <= known:
            raise MultiBusGatewayContractError(
                reason="Ethernet contracts may reference only CAN nodes"
            )
    route_ids = [route.identifier for route in command.gateway_routes]
    if len(route_ids) != len(set(route_ids)):
        raise MultiBusGatewayContractError(reason="gateway route identifiers must be unique")
    for route in command.gateway_routes:
        if roles.get(route.gateway_node_id) != "gateway":
            raise MultiBusGatewayContractError(reason="gateway route node must have gateway role")
        source_length = _payload_length(
            network, route.source_protocol, route.source_contract_id, lin, ethernet
        )
        destination_length = _payload_length(
            network, route.destination_protocol, route.destination_contract_id, lin, ethernet
        )
        if source_length != destination_length:
            raise MultiBusGatewayContractError(
                reason="transparent routes require equal source and destination payload lengths"
            )


def _payload_length(
    network: CanNetwork,
    protocol: VehicleBusProtocol,
    identifier: str,
    lin: dict[str, tuple[LinFrameContract, int]],
    ethernet: dict[str, tuple[EthernetMessageContract, int]],
) -> int:
    if protocol is VehicleBusProtocol.CAN:
        return _contract(network, identifier).dlc
    try:
        if protocol is VehicleBusProtocol.LIN:
            return lin[identifier][0].payload_length
        return ethernet[identifier][0].payload_length
    except KeyError as exc:
        raise MultiBusGatewayContractError(
            reason=f"{protocol.value} contract does not exist"
        ) from exc


async def _existing(
    session: AsyncSession, network: CanNetwork, command_id: str, request: dict[str, Any]
) -> MultiBusGatewayExecution | None:
    item = await session.scalar(
        select(MultiBusGatewayExecution).where(
            MultiBusGatewayExecution.network_id == network.id,
            MultiBusGatewayExecution.command_id == command_id,
        )
    )
    if item is not None and item.request != request:
        raise MultiBusGatewayCommandConflictError()
    return item


async def configure_multibus(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: MultiBusConfigurationCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[MultiBusGatewayExecution, CanNetwork, bool]:
    network = await require_can_network(session, vehicle=vehicle, for_update=True)
    request = command.model_dump(mode="json")
    if item := await _existing(session, network, command.command_id, request):
        return item, network, True
    if command.expected_version != network.version:
        raise CanNetworkVersionConflictError(current_version=network.version)
    _validate_configuration(network, command)
    previous_version = network.version
    network.lin_channels = [item.model_dump(mode="json") for item in command.lin_channels]
    network.ethernet_segments = [item.model_dump(mode="json") for item in command.ethernet_segments]
    network.gateway_routes = [item.model_dump(mode="json") for item in command.gateway_routes]
    network.version += 1
    result: dict[str, Any] = {
        "lin_channel_count": len(command.lin_channels),
        "lin_frame_count": sum(len(item.frames) for item in command.lin_channels),
        "ethernet_segment_count": len(command.ethernet_segments),
        "ethernet_message_count": sum(len(item.messages) for item in command.ethernet_segments),
        "gateway_route_count": len(command.gateway_routes),
    }
    execution = MultiBusGatewayExecution(
        network_id=network.id,
        command_id=command.command_id,
        operation="configure",
        route_id=None,
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
        **result,
        "previous_version": previous_version,
        "network_version": network.version,
    }
    enqueue_event(
        session,
        event_type="atep.vehicle.multibus.configured.v1",
        aggregate_type="can_network",
        aggregate_id=network.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="vehicle.multibus_configured",
        resource_type="can_network",
        resource_id=network.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return execution, network, False


def _stored_route(network: CanNetwork, route_id: str) -> GatewayRouteContract:
    for item in network.gateway_routes or []:
        route = GatewayRouteContract.model_validate(item)
        if route.identifier == route_id:
            return route
    raise MultiBusGatewayContractError(reason="gateway route does not exist")


def _stored_destination(
    network: CanNetwork, route: GatewayRouteContract
) -> tuple[int, int, dict[str, Any]]:
    if route.destination_protocol is VehicleBusProtocol.CAN:
        contract = _contract(network, route.destination_contract_id)
        timing = frame_timing(contract, network)
        return (
            contract.dlc,
            timing.duration_us,
            {
                "bit_count": timing.bit_count,
                "bitrate_kbps": network.bitrate_kbps,
            },
        )
    if route.destination_protocol is VehicleBusProtocol.LIN:
        for channel_data in network.lin_channels or []:
            bitrate = int(channel_data["bitrate_kbps"])
            for frame_data in channel_data["frames"]:
                frame = LinFrameContract.model_validate(frame_data)
                if frame.identifier == route.destination_contract_id:
                    bits = 43 + (10 * frame.payload_length)
                    return (
                        frame.payload_length,
                        ceil(bits * 1000 / bitrate),
                        {
                            "bit_count": bits,
                            "bitrate_kbps": bitrate,
                        },
                    )
    else:
        for segment_data in network.ethernet_segments or []:
            speed = int(segment_data["speed_mbps"])
            for message_data in segment_data["messages"]:
                message = EthernetMessageContract.model_validate(message_data)
                if message.identifier == route.destination_contract_id:
                    bits = (38 + message.payload_length) * 8
                    return (
                        message.payload_length,
                        ceil(bits / speed),
                        {
                            "bit_count": bits,
                            "speed_mbps": speed,
                        },
                    )
    raise MultiBusGatewayContractError(reason="route destination contract does not exist")


async def execute_gateway_route(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: GatewayRouteCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[MultiBusGatewayExecution, CanNetwork, bool]:
    network = await require_can_network(session, vehicle=vehicle, for_update=True)
    request = command.model_dump(mode="json")
    if item := await _existing(session, network, command.command_id, request):
        return item, network, True
    if command.expected_version != network.version:
        raise CanNetworkVersionConflictError(current_version=network.version)
    route = _stored_route(network, command.route_id)
    payload_length, duration_us, timing = _stored_destination(network, route)
    if len(command.payload) != payload_length:
        raise MultiBusGatewayContractError(reason="payload length must equal the routed contract")
    previous_version = network.version
    sequence = network.next_sequence
    started_at_us = network.simulation_time_us + command.advance_time_us
    completed_at_us = started_at_us + duration_us
    network.simulation_time_us = completed_at_us
    network.next_sequence += 1
    network.version += 1
    result: dict[str, Any] = {
        "sequence": sequence,
        "source_protocol": route.source_protocol.value,
        "source_contract_id": route.source_contract_id,
        "destination_protocol": route.destination_protocol.value,
        "destination_contract_id": route.destination_contract_id,
        "gateway_node_id": str(route.gateway_node_id),
        "payload_length": payload_length,
        "started_at_us": started_at_us,
        "completed_at_us": completed_at_us,
        "duration_us": duration_us,
        **timing,
    }
    execution = MultiBusGatewayExecution(
        network_id=network.id,
        command_id=command.command_id,
        operation="route",
        route_id=route.identifier,
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
        "route_id": route.identifier,
        **result,
        "previous_version": previous_version,
        "network_version": network.version,
    }
    enqueue_event(
        session,
        event_type="atep.vehicle.gateway.routed.v1",
        aggregate_type="can_network",
        aggregate_id=network.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="vehicle.gateway_routed",
        resource_type="can_network",
        resource_id=network.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return execution, network, False


async def list_gateway_executions(
    session: AsyncSession, *, network: CanNetwork, limit: int, offset: int
) -> tuple[list[MultiBusGatewayExecution], int]:
    query = select(MultiBusGatewayExecution).where(
        MultiBusGatewayExecution.network_id == network.id
    )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(MultiBusGatewayExecution.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total or 0)


async def require_gateway_execution(
    session: AsyncSession, *, network: CanNetwork, command_id: str
) -> MultiBusGatewayExecution:
    item = await session.scalar(
        select(MultiBusGatewayExecution).where(
            MultiBusGatewayExecution.network_id == network.id,
            MultiBusGatewayExecution.command_id == command_id,
        )
    )
    if item is None:
        raise ResourceNotFoundError("multibus_gateway_execution")
    return item
