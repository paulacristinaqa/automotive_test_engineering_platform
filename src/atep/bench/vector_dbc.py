"""Render an ATEP CAN network and DBC catalogue as a Vector-compatible DBC file."""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from atep.can_network.schemas import (
    CanDbcByteOrder,
    CanDbcMessage,
    CanDbcSignal,
    CanFrameContract,
    CanFrameFormat,
    CanFrameProtocol,
)

EXTENDED_ID_FLAG = 0x80000000
NO_RECEIVER = "Vector__XXX"
DBC_ENCODING = "cp1252"

# Index into the VFrameFormat enum used by Vector CANdb++ and CANoe.
_FRAME_FORMAT_INDEX = {
    (CanFrameFormat.STANDARD, CanFrameProtocol.CLASSIC): 0,
    (CanFrameFormat.EXTENDED, CanFrameProtocol.CLASSIC): 1,
    (CanFrameFormat.STANDARD, CanFrameProtocol.FD): 14,
    (CanFrameFormat.EXTENDED, CanFrameProtocol.FD): 15,
}

_NEW_SYMBOLS = (
    "NS_DESC_",
    "CM_",
    "BA_DEF_",
    "BA_",
    "VAL_",
    "CAT_DEF_",
    "CAT_",
    "FILTER",
    "BA_DEF_DEF_",
    "EV_DATA_",
    "ENVVAR_DATA_",
    "SGTYPE_",
    "SGTYPE_VAL_",
    "BA_DEF_SGTYPE_",
    "BA_SGTYPE_",
    "SIG_TYPE_REF_",
    "VAL_TABLE_",
    "SIG_GROUP_",
    "SIG_VALTYPE_",
    "SIGTYPE_VALTYPE_",
    "BO_TX_BU_",
    "BA_DEF_REL_",
    "BA_REL_",
    "BA_DEF_DEF_REL_",
    "BU_SG_REL_",
    "BU_EV_REL_",
    "BU_BO_REL_",
    "SG_MUL_VAL_",
)


class DbcExportError(ValueError):
    """The network cannot be expressed as a valid DBC file."""


@dataclass(frozen=True)
class DbcNode:
    node_id: UUID
    name: str


@dataclass(frozen=True)
class VectorNetworkSpec:
    """Everything needed to render one CAN network as a DBC file."""

    network_identifier: str
    display_name: str
    revision: str
    bitrate_kbps: int
    can_fd_enabled: bool
    data_bitrate_kbps: int | None
    nodes: list[DbcNode]
    frames: list[CanFrameContract]
    messages: dict[str, CanDbcMessage] = field(default_factory=dict)


def dbc_identifier(value: str, *, fallback_prefix: str = "N") -> str:
    """Return a C-style identifier that DBC tools accept."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", value.strip())
    if not name or not name[0].isalpha():
        name = f"{fallback_prefix}_{name}"
    return name


def _number(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return text


def _quoted(value: str) -> str:
    return '"' + value.replace('"', "'").replace("\\", "/") + '"'


def _physical_range(signal: CanDbcSignal) -> tuple[Decimal, Decimal]:
    if signal.signed:
        raw_min = -(1 << (signal.bit_length - 1))
        raw_max = (1 << (signal.bit_length - 1)) - 1
    else:
        raw_min, raw_max = 0, (1 << signal.bit_length) - 1
    minimum = signal.minimum
    if minimum is None:
        minimum = Decimal(raw_min) * signal.factor + signal.offset
    maximum = signal.maximum
    if maximum is None:
        maximum = Decimal(raw_max) * signal.factor + signal.offset
    return minimum, maximum


def _unique_names(pairs: list[tuple[str, str]], kind: str) -> dict[str, str]:
    """Map source identifiers to DBC names, rejecting collisions."""
    mapped: dict[str, str] = {}
    owners: dict[str, str] = {}
    for source, name in pairs:
        if name in owners and owners[name] != source:
            raise DbcExportError(
                f"{kind} names {owners[name]!r} and {source!r} both map to DBC name {name!r}"
            )
        owners[name] = source
        mapped[source] = name
    return mapped


def dbc_message_id(frame: CanFrameContract) -> int:
    if frame.frame_format is CanFrameFormat.EXTENDED:
        return frame.frame_id | EXTENDED_ID_FLAG
    return frame.frame_id


def _signal_line(signal: CanDbcSignal, receivers: str) -> str:
    order = "1" if signal.byte_order is CanDbcByteOrder.INTEL else "0"
    sign = "-" if signal.signed else "+"
    minimum, maximum = _physical_range(signal)
    return (
        f" SG_ {signal.identifier} : {signal.start_bit}|{signal.bit_length}@{order}{sign}"
        f" ({_number(signal.factor)},{_number(signal.offset)})"
        f" [{_number(minimum)}|{_number(maximum)}] {_quoted(signal.unit)} {receivers}"
    )


def render_dbc(spec: VectorNetworkSpec) -> str:
    """Render the network as DBC text. Identical inputs give identical output."""
    node_names = _unique_names(
        [
            (str(node.node_id), dbc_identifier(node.name, fallback_prefix="ECU"))
            for node in spec.nodes
        ],
        "Node",
    )
    frames = sorted(spec.frames, key=lambda item: (dbc_message_id(item), item.identifier))
    message_names = _unique_names(
        [
            (frame.identifier, dbc_identifier(frame.identifier, fallback_prefix="MSG"))
            for frame in frames
        ],
        "Message",
    )
    unknown = set(spec.messages) - {frame.identifier for frame in frames}
    if unknown:
        raise DbcExportError(f"DBC messages reference unknown frame contracts: {sorted(unknown)}")

    def node_name(node_id: UUID) -> str:
        try:
            return node_names[str(node_id)]
        except KeyError as error:
            raise DbcExportError(f"frame references unknown node {node_id}") from error

    lines = [f"VERSION {_quoted(spec.revision)}", "", "", "NS_ :"]
    lines.extend(f"\t{symbol}" for symbol in _NEW_SYMBOLS)
    lines.extend(
        ["", "BS_:", "", "BU_: " + " ".join(node_names[str(n.node_id)] for n in spec.nodes)]
    )
    lines.append("")

    for frame in frames:
        producer = node_name(frame.producer_node_id)
        lines.append(
            f"BO_ {dbc_message_id(frame)} {message_names[frame.identifier]}: {frame.dlc} {producer}"
        )
        receivers = ",".join(node_name(item) for item in frame.consumer_node_ids) or NO_RECEIVER
        message = spec.messages.get(frame.identifier)
        if message is not None:
            for signal in sorted(message.signals, key=lambda item: item.start_bit):
                lines.append(_signal_line(signal, receivers))
        lines.append("")

    lines.append("")
    lines.append(f"CM_ {_quoted(f'ATEP network {spec.network_identifier}: {spec.display_name}')};")
    for node in spec.nodes:
        lines.append(
            f"CM_ BU_ {node_names[str(node.node_id)]} {_quoted(f'ATEP ECU {node.node_id}')};"
        )
    for frame in frames:
        lines.append(
            f"CM_ BO_ {dbc_message_id(frame)} {_quoted(f'ATEP frame contract {frame.identifier}')};"
        )

    frame_formats = ",".join(
        _quoted(name)
        for name in (
            ["StandardCAN", "ExtendedCAN"]
            + ["reserved"] * 12
            + ["StandardCAN_FD", "ExtendedCAN_FD"]
        )
    )
    lines.extend(
        [
            'BA_DEF_  "BusType" STRING ;',
            'BA_DEF_  "DBName" STRING ;',
            'BA_DEF_  "Baudrate" INT 1000 1000000;',
            'BA_DEF_  "BaudrateCANFD" INT 1000 16000000;',
            f'BA_DEF_ BO_  "VFrameFormat" ENUM  {frame_formats};',
            'BA_DEF_ BO_  "CANFD_BRS" ENUM  "0","1";',
            'BA_DEF_DEF_  "BusType" "CAN";',
            'BA_DEF_DEF_  "DBName" "";',
            'BA_DEF_DEF_  "Baudrate" 500000;',
            'BA_DEF_DEF_  "BaudrateCANFD" 2000000;',
            'BA_DEF_DEF_  "VFrameFormat" "StandardCAN";',
            'BA_DEF_DEF_  "CANFD_BRS" "0";',
            f'BA_ "BusType" {_quoted("CAN FD" if spec.can_fd_enabled else "CAN")};',
            f'BA_ "DBName" {_quoted(dbc_identifier(spec.network_identifier))};',
            f'BA_ "Baudrate" {spec.bitrate_kbps * 1000};',
        ]
    )
    if spec.can_fd_enabled and spec.data_bitrate_kbps is not None:
        lines.append(f'BA_ "BaudrateCANFD" {spec.data_bitrate_kbps * 1000};')
    for frame in frames:
        index = _FRAME_FORMAT_INDEX[(frame.frame_format, frame.protocol)]
        if index:
            lines.append(f'BA_ "VFrameFormat" BO_ {dbc_message_id(frame)} {index};')
        if frame.bitrate_switch:
            lines.append(f'BA_ "CANFD_BRS" BO_ {dbc_message_id(frame)} 1;')
    lines.append("")
    return "\n".join(lines)


def encode_dbc(text: str) -> bytes:
    """Encode DBC text the way Vector tools expect (Windows-1252, CRLF)."""
    return text.replace("\n", "\r\n").encode(DBC_ENCODING, errors="replace")
