"""Load ATEP CAN evidence for Vector DBC and trace exports. Read-only."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.bench.vector_dbc import DbcExportError, DbcNode, VectorNetworkSpec, render_dbc
from atep.bench.vector_trace import TraceFrame
from atep.can_network.models import CanDbcCatalogue, CanFrameTransmission, CanNetwork
from atep.can_network.schemas import (
    CanDbcMessage,
    CanFrameContract,
    CanFrameFormat,
    CanFrameProtocol,
    CanNode,
)
from atep.core.errors import CanNetworkContractError
from atep.ecus.models import ElectronicControlUnit

MAX_TRACE_FRAMES = 10_000


@dataclass(frozen=True)
class TracePage:
    frames: list[TraceFrame]
    last_sequence: int | None
    truncated: bool


async def build_network_spec(session: AsyncSession, *, network: CanNetwork) -> VectorNetworkSpec:
    catalogue = await session.scalar(
        select(CanDbcCatalogue).where(CanDbcCatalogue.network_id == network.id)
    )
    node_ids = [CanNode.model_validate(item).ecu_id for item in network.nodes]
    result = await session.execute(
        select(ElectronicControlUnit.id, ElectronicControlUnit.identifier).where(
            ElectronicControlUnit.id.in_(node_ids)
        )
    )
    names = {row[0]: row[1] for row in result.all()}
    messages: dict[str, CanDbcMessage] = {}
    if catalogue is not None:
        for item in catalogue.messages:
            message = CanDbcMessage.model_validate(item)
            messages[message.contract_id] = message
    return VectorNetworkSpec(
        network_identifier=network.identifier,
        display_name=network.display_name,
        revision=catalogue.revision if catalogue is not None else f"network-v{network.version}",
        bitrate_kbps=network.bitrate_kbps,
        can_fd_enabled=network.can_fd_enabled,
        data_bitrate_kbps=network.data_bitrate_kbps,
        nodes=[
            DbcNode(node_id=node_id, name=names.get(node_id, f"ECU_{node_id.hex}"))
            for node_id in node_ids
        ],
        frames=[CanFrameContract.model_validate(item) for item in network.frame_contracts],
        messages=messages,
    )


async def export_dbc(session: AsyncSession, *, network: CanNetwork) -> str:
    spec = await build_network_spec(session, network=network)
    try:
        return render_dbc(spec)
    except DbcExportError as error:
        raise CanNetworkContractError(reason=str(error)) from error


def trace_frame(transmission: CanFrameTransmission) -> TraceFrame:
    return TraceFrame(
        timestamp_us=transmission.transmission_time_us,
        arbitration_id=transmission.frame_id,
        is_extended_id=transmission.frame_format == CanFrameFormat.EXTENDED.value,
        data=bytes(transmission.payload),
        is_fd=transmission.protocol == CanFrameProtocol.FD.value,
        bitrate_switch=transmission.bitrate_switch,
    )


async def load_trace_page(
    session: AsyncSession, *, network: CanNetwork, after_sequence: int, limit: int
) -> TracePage:
    if not 1 <= limit <= MAX_TRACE_FRAMES:
        raise ValueError(f"trace limit must be between 1 and {MAX_TRACE_FRAMES}")
    result = await session.execute(
        select(CanFrameTransmission)
        .where(
            CanFrameTransmission.network_id == network.id,
            CanFrameTransmission.sequence > after_sequence,
        )
        .order_by(CanFrameTransmission.sequence.asc())
        .limit(limit + 1)
    )
    rows = list(result.scalars().all())
    truncated = len(rows) > limit
    rows = rows[:limit]
    return TracePage(
        frames=[trace_frame(row) for row in rows],
        last_sequence=rows[-1].sequence if rows else None,
        truncated=truncated,
    )
