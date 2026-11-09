"""Render ATEP CAN frame evidence as Vector ASC and BLF traces."""

import io
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

import can
from can.io.blf import BLFWriter
from can.util import len2dlc

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_FD_FLAG = 1 << 12
_BRS_FLAG = 1 << 13
START_MARKER = "Start of measurement"


@dataclass(frozen=True)
class TraceFrame:
    """One CAN frame on the bench timeline, in logical microseconds."""

    timestamp_us: int
    arbitration_id: int
    is_extended_id: bool
    data: bytes
    is_fd: bool = False
    bitrate_switch: bool = False
    channel: int = 1

    def __post_init__(self) -> None:
        if self.timestamp_us < 0:
            raise ValueError("trace timestamps must not be negative")
        if self.channel < 1:
            raise ValueError("trace channels start at 1")
        if self.bitrate_switch and not self.is_fd:
            raise ValueError("bitrate switch requires a CAN FD frame")
        if len(self.data) > (64 if self.is_fd else 8):
            raise ValueError("payload is longer than the frame type allows")


def anchor_from(moment: datetime) -> datetime:
    """Measurement start in UTC, truncated to the millisecond that BLF can store."""
    value = moment.astimezone(UTC) if moment.tzinfo else moment.replace(tzinfo=UTC)
    return value.replace(microsecond=(value.microsecond // 1000) * 1000)


def _asc_date(moment: datetime) -> str:
    # Locale-independent English names, as Vector tools write them.
    return (
        f"{_WEEKDAYS[moment.weekday()]} {_MONTHS[moment.month - 1]} {moment.day:02d} "
        f"{moment:%H:%M:%S}.{moment.microsecond // 1000:03d} {moment.year}"
    )


def _asc_time(timestamp_us: int) -> str:
    return f"{timestamp_us // 1_000_000:>4}.{timestamp_us % 1_000_000:06d}"


def _asc_line(frame: TraceFrame) -> str:
    arb_id = f"{frame.arbitration_id:X}" + ("x" if frame.is_extended_id else "")
    data = frame.data.hex(" ").upper()
    if not frame.is_fd:
        line = f"{frame.channel}  {arb_id:<15} Rx   d {len(frame.data):x} {data}".rstrip()
        return f"{_asc_time(frame.timestamp_us)} {line}"
    flags = _FD_FLAG | (_BRS_FLAG if frame.bitrate_switch else 0)
    fields = [
        "CANFD",
        f"{frame.channel:>3}",
        "Rx  ",
        f"{arb_id:>8}  {'':>32}",
        "1" if frame.bitrate_switch else "0",
        "0",
        f"{len2dlc(len(frame.data)):x}",
        f"{len(frame.data):>2}",
    ]
    if data:
        fields.append(data)
    fields.extend([f"{0:>8}", f"{0:>4}", f"{flags:>8X}", f"{0:>8}"] + [f"{0:>8}"] * 4)
    return f"{_asc_time(frame.timestamp_us)} " + " ".join(fields)


def render_asc(frames: Iterable[TraceFrame], *, measurement_start: datetime) -> str:
    """Render frames as a Vector ASC trace with timestamps relative to measurement start."""
    start = anchor_from(measurement_start)
    date = _asc_date(start)
    lines = [
        f"date {date}",
        "base hex  timestamps absolute",
        "internal events logged",
        f"Begin Triggerblock {date}",
        f"{_asc_time(0)} {START_MARKER}",
    ]
    lines.extend(_asc_line(frame) for frame in sorted(frames, key=lambda item: item.timestamp_us))
    lines.append("End TriggerBlock")
    lines.append("")
    return "\n".join(lines)


def to_message(frame: TraceFrame, *, start_s: float = 0.0) -> can.Message:
    return can.Message(
        timestamp=start_s + frame.timestamp_us / 1_000_000,
        arbitration_id=frame.arbitration_id,
        is_extended_id=frame.is_extended_id,
        is_fd=frame.is_fd,
        bitrate_switch=frame.bitrate_switch,
        data=frame.data,
        channel=frame.channel - 1,
        check=True,
    )


class _RetainedBuffer(io.BytesIO):
    """BLFWriter closes its file on stop; keep the bytes readable afterwards."""

    def close(self) -> None:
        return None


def render_blf(frames: Iterable[TraceFrame], *, measurement_start: datetime) -> bytes:
    """Render frames as a Vector BLF trace starting at the measurement start."""
    start_s = anchor_from(measurement_start).timestamp()
    buffer = _RetainedBuffer()
    writer = BLFWriter(buffer)
    # The marker pins the BLF start time to the measurement start, not the first frame.
    writer.log_event(START_MARKER, start_s)
    for frame in sorted(frames, key=lambda item: item.timestamp_us):
        writer.on_message_received(to_message(frame, start_s=start_s))
    writer.stop()
    return buffer.getvalue()
