from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.can_network.models import CanDbcCatalogue, CanNetwork, CanSignalCodecExecution
from atep.can_network.schemas import (
    CanDbcByteOrder,
    CanDbcCatalogueCreate,
    CanDbcMessage,
    CanDbcSignal,
    CanSignalDecodeCommand,
    CanSignalEncodeCommand,
)
from atep.can_network.service import _contract, require_can_network
from atep.core.errors import (
    CanDbcCatalogueAlreadyExistsError,
    CanNetworkContractError,
    CanNetworkVersionConflictError,
    CanSignalCodecCommandConflictError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


def dbc_bit_positions(signal: CanDbcSignal) -> list[int]:
    if signal.byte_order is CanDbcByteOrder.INTEL:
        return [signal.start_bit + index for index in range(signal.bit_length)]
    positions = [signal.start_bit]
    for _ in range(1, signal.bit_length):
        current = positions[-1]
        positions.append(current + 15 if current % 8 == 0 else current - 1)
    return positions


def _validate_message(message: CanDbcMessage, *, dlc: int) -> None:
    occupied: set[int] = set()
    for signal in message.signals:
        positions = dbc_bit_positions(signal)
        if max(positions) >= dlc * 8:
            raise CanNetworkContractError(
                reason=f"DBC signal {signal.identifier} exceeds the contracted DLC"
            )
        if occupied.intersection(positions):
            raise CanNetworkContractError(reason="DBC signals may not overlap within a message")
        occupied.update(positions)


def _message(catalogue: CanDbcCatalogue, contract_id: str) -> CanDbcMessage:
    for item in catalogue.messages:
        message = CanDbcMessage.model_validate(item)
        if message.contract_id == contract_id:
            return message
    raise CanNetworkContractError(reason="DBC message does not exist for the frame contract")


def _raw_bounds(signal: CanDbcSignal) -> tuple[int, int]:
    if signal.signed:
        return -(1 << (signal.bit_length - 1)), (1 << (signal.bit_length - 1)) - 1
    return 0, (1 << signal.bit_length) - 1


def _physical_to_raw(signal: CanDbcSignal, physical: Decimal) -> int:
    if signal.minimum is not None and physical < signal.minimum:
        raise CanNetworkContractError(reason=f"signal {signal.identifier} is below its minimum")
    if signal.maximum is not None and physical > signal.maximum:
        raise CanNetworkContractError(reason=f"signal {signal.identifier} is above its maximum")
    raw_decimal = (physical - signal.offset) / signal.factor
    integral = raw_decimal.to_integral_value()
    if raw_decimal != integral:
        raise CanNetworkContractError(
            reason=f"signal {signal.identifier} is not exactly representable"
        )
    raw = int(integral)
    minimum, maximum = _raw_bounds(signal)
    if raw < minimum or raw > maximum:
        raise CanNetworkContractError(reason=f"signal {signal.identifier} exceeds its raw range")
    return raw


def _write_raw(payload: bytearray, signal: CanDbcSignal, raw: int) -> None:
    encoded = raw & ((1 << signal.bit_length) - 1)
    positions = dbc_bit_positions(signal)
    for index, position in enumerate(positions):
        raw_index = (
            index
            if signal.byte_order is CanDbcByteOrder.INTEL
            else signal.bit_length - 1 - index
        )
        if encoded & (1 << raw_index):
            payload[position // 8] |= 1 << (position % 8)


def _read_raw(payload: list[int], signal: CanDbcSignal) -> int:
    encoded = 0
    for index, position in enumerate(dbc_bit_positions(signal)):
        raw_index = (
            index
            if signal.byte_order is CanDbcByteOrder.INTEL
            else signal.bit_length - 1 - index
        )
        if payload[position // 8] & (1 << (position % 8)):
            encoded |= 1 << raw_index
    if signal.signed and encoded & (1 << (signal.bit_length - 1)):
        return encoded - (1 << signal.bit_length)
    return encoded


def encode_message(
    message: CanDbcMessage, *, dlc: int, values: dict[str, Decimal]
) -> tuple[list[int], dict[str, int], dict[str, Decimal]]:
    declared = {signal.identifier for signal in message.signals}
    if set(values) != declared:
        raise CanNetworkContractError(
            reason="encode values must exactly match declared DBC signals"
        )
    payload = bytearray(dlc)
    raw_values: dict[str, int] = {}
    physical_values: dict[str, Decimal] = {}
    for signal in message.signals:
        physical = values[signal.identifier]
        raw = _physical_to_raw(signal, physical)
        _write_raw(payload, signal, raw)
        raw_values[signal.identifier] = raw
        physical_values[signal.identifier] = physical
    return list(payload), raw_values, physical_values


def decode_message(
    message: CanDbcMessage, *, payload: list[int]
) -> tuple[dict[str, int], dict[str, Decimal]]:
    raw_values: dict[str, int] = {}
    physical_values: dict[str, Decimal] = {}
    for signal in message.signals:
        raw = _read_raw(payload, signal)
        physical = (Decimal(raw) * signal.factor) + signal.offset
        raw_values[signal.identifier] = raw
        physical_values[signal.identifier] = physical
    return raw_values, physical_values


async def create_dbc_catalogue(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: CanDbcCatalogueCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[CanDbcCatalogue, CanNetwork]:
    network = await require_can_network(session, vehicle=vehicle, for_update=True)
    existing = await session.scalar(
        select(CanDbcCatalogue).where(CanDbcCatalogue.network_id == network.id)
    )
    if existing is not None:
        raise CanDbcCatalogueAlreadyExistsError()
    if command.expected_version != network.version:
        raise CanNetworkVersionConflictError(current_version=network.version)
    for message in command.messages:
        contract = _contract(network, message.contract_id)
        _validate_message(message, dlc=contract.dlc)
    network.version += 1
    catalogue = CanDbcCatalogue(
        network_id=network.id,
        identifier=command.identifier,
        display_name=command.display_name.strip(),
        revision=command.revision.strip(),
        messages=[message.model_dump(mode="json") for message in command.messages],
        network_version=network.version,
        created_by_user_id=actor_user_id,
    )
    session.add(catalogue)
    await session.flush()
    evidence = {
        "vehicle_id": vehicle.identifier,
        "network_id": network.identifier,
        "catalogue_id": catalogue.identifier,
        "revision": catalogue.revision,
        "message_count": len(catalogue.messages),
        "signal_count": sum(len(message.signals) for message in command.messages),
        "network_version": network.version,
    }
    enqueue_event(
        session,
        event_type="atep.can.dbc.catalogue.created.v1",
        aggregate_type="can_network",
        aggregate_id=network.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="can.dbc_catalogue_created",
        resource_type="can_network",
        resource_id=network.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return catalogue, network


async def require_dbc_catalogue(
    session: AsyncSession, *, network: CanNetwork
) -> CanDbcCatalogue:
    catalogue = await session.scalar(
        select(CanDbcCatalogue).where(CanDbcCatalogue.network_id == network.id)
    )
    if catalogue is None:
        raise ResourceNotFoundError("can_dbc_catalogue")
    return catalogue


async def _existing_execution(
    session: AsyncSession,
    *,
    network: CanNetwork,
    command_id: str,
    request: dict[str, Any],
) -> CanSignalCodecExecution | None:
    existing = await session.scalar(
        select(CanSignalCodecExecution).where(
            CanSignalCodecExecution.network_id == network.id,
            CanSignalCodecExecution.command_id == command_id,
        )
    )
    if existing is not None and existing.request != request:
        raise CanSignalCodecCommandConflictError()
    return existing


async def _record_codec(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    network: CanNetwork,
    command_id: str,
    operation: str,
    contract_id: str,
    request: dict[str, Any],
    payload: list[int],
    raw_values: dict[str, int],
    physical_values: dict[str, Decimal],
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> CanSignalCodecExecution:
    result: dict[str, Any] = {
        "payload": payload,
        "raw_values": raw_values,
        "physical_values": {key: str(value) for key, value in physical_values.items()},
    }
    execution = CanSignalCodecExecution(
        network_id=network.id,
        command_id=command_id,
        operation=operation,
        contract_id=contract_id,
        request=request,
        result=result,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    evidence = {
        "vehicle_id": vehicle.identifier,
        "network_id": network.identifier,
        "command_id": command_id,
        "operation": operation,
        "contract_id": contract_id,
        "signal_count": len(raw_values),
        "dlc": len(payload),
    }
    enqueue_event(
        session,
        event_type="atep.can.signal.codec.completed.v1",
        aggregate_type="can_network",
        aggregate_id=network.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action=f"can.signal_{operation}",
        resource_type="can_network",
        resource_id=network.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return execution


async def encode_signals(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: CanSignalEncodeCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[CanSignalCodecExecution, CanNetwork, bool]:
    network = await require_can_network(session, vehicle=vehicle, for_update=True)
    request: dict[str, Any] = {"operation": "encode", **command.model_dump(mode="json")}
    existing = await _existing_execution(
        session, network=network, command_id=command.command_id, request=request
    )
    if existing is not None:
        return existing, network, True
    catalogue = await require_dbc_catalogue(session, network=network)
    message = _message(catalogue, command.contract_id)
    contract = _contract(network, command.contract_id)
    payload, raw_values, physical_values = encode_message(
        message, dlc=contract.dlc, values=command.values
    )
    execution = await _record_codec(
        session,
        vehicle=vehicle,
        network=network,
        command_id=command.command_id,
        operation="encode",
        contract_id=command.contract_id,
        request=request,
        payload=payload,
        raw_values=raw_values,
        physical_values=physical_values,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
    )
    return execution, network, False


async def decode_signals(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: CanSignalDecodeCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[CanSignalCodecExecution, CanNetwork, bool]:
    network = await require_can_network(session, vehicle=vehicle, for_update=True)
    request: dict[str, Any] = {"operation": "decode", **command.model_dump(mode="json")}
    existing = await _existing_execution(
        session, network=network, command_id=command.command_id, request=request
    )
    if existing is not None:
        return existing, network, True
    catalogue = await require_dbc_catalogue(session, network=network)
    message = _message(catalogue, command.contract_id)
    contract = _contract(network, command.contract_id)
    if len(command.payload) != contract.dlc:
        raise CanNetworkContractError(reason="payload length must equal the frame contract DLC")
    raw_values, physical_values = decode_message(message, payload=command.payload)
    execution = await _record_codec(
        session,
        vehicle=vehicle,
        network=network,
        command_id=command.command_id,
        operation="decode",
        contract_id=command.contract_id,
        request=request,
        payload=command.payload,
        raw_values=raw_values,
        physical_values=physical_values,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
    )
    return execution, network, False


async def list_codec_executions(
    session: AsyncSession, *, network: CanNetwork, limit: int, offset: int
) -> tuple[list[CanSignalCodecExecution], int]:
    query = select(CanSignalCodecExecution).where(
        CanSignalCodecExecution.network_id == network.id
    )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(CanSignalCodecExecution.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def require_codec_execution(
    session: AsyncSession, *, network: CanNetwork, command_id: str
) -> CanSignalCodecExecution:
    execution = await session.scalar(
        select(CanSignalCodecExecution).where(
            CanSignalCodecExecution.network_id == network.id,
            CanSignalCodecExecution.command_id == command_id,
        )
    )
    if execution is None:
        raise ResourceNotFoundError("can_signal_codec_execution")
    return execution
