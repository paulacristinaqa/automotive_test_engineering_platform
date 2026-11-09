"""Bench bus: a python-can bus restricted to known interfaces, plus frame replay."""

import time
from collections.abc import Callable, Iterable
from enum import StrEnum

import can
from pydantic import BaseModel, ConfigDict, Field, model_validator

from atep.bench.vector_trace import TraceFrame, to_message


class BenchInterface(StrEnum):
    VIRTUAL = "virtual"
    SOCKETCAN = "socketcan"
    VECTOR = "vector"
    PCAN = "pcan"
    SLCAN = "slcan"


class BenchBusConfig(BaseModel):
    """Which python-can interface the bench uses. `virtual` needs no hardware."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    interface: BenchInterface = BenchInterface.VIRTUAL
    channel: str = Field(default="atep-bench", min_length=1, max_length=80)
    bitrate_kbps: int = Field(default=500, ge=10, le=1000)
    fd: bool = False
    data_bitrate_kbps: int | None = Field(default=None, ge=10, le=8000)
    receive_own_messages: bool = False

    @model_validator(mode="after")
    def validate_fd_bitrate(self) -> "BenchBusConfig":
        if self.data_bitrate_kbps is not None and not self.fd:
            raise ValueError("a data-phase bitrate requires CAN FD")
        return self


def open_bench_bus(config: BenchBusConfig) -> can.BusABC:
    if not config.fd:
        return can.Bus(
            channel=config.channel,
            interface=config.interface.value,
            bitrate=config.bitrate_kbps * 1000,
            receive_own_messages=config.receive_own_messages,
        )
    data_bitrate = (config.data_bitrate_kbps or config.bitrate_kbps) * 1000
    return can.Bus(
        channel=config.channel,
        interface=config.interface.value,
        bitrate=config.bitrate_kbps * 1000,
        receive_own_messages=config.receive_own_messages,
        fd=True,
        data_bitrate=data_bitrate,
    )


def from_message(message: can.Message, *, start_s: float = 0.0) -> TraceFrame:
    """Convert a received python-can message back to a bench frame."""
    channel = message.channel if isinstance(message.channel, int) else 0
    return TraceFrame(
        timestamp_us=max(round((message.timestamp - start_s) * 1_000_000), 0),
        arbitration_id=message.arbitration_id,
        is_extended_id=message.is_extended_id,
        data=bytes(message.data),
        is_fd=message.is_fd,
        bitrate_switch=message.bitrate_switch,
        channel=channel + 1,
        is_error_frame=message.is_error_frame,
    )


def replay_frames(
    bus: can.BusABC,
    frames: Iterable[TraceFrame],
    *,
    realtime: bool = False,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Send frames in timestamp order.

    Deterministic mode sends at once. Real-time mode waits until each frame's
    logical timestamp, measured from the first call, has elapsed.
    """
    ordered = sorted(frames, key=lambda item: item.timestamp_us)
    started = clock()
    for frame in ordered:
        if realtime:
            delay = started + frame.timestamp_us / 1_000_000 - clock()
            if delay > 0:
                sleep(delay)
        bus.send(to_message(frame))
    return len(ordered)


def collect_frames(bus: can.BusABC, *, count: int, timeout_s: float = 2.0) -> list[can.Message]:
    """Receive up to `count` messages, stopping early when the bus stays quiet."""
    received: list[can.Message] = []
    while len(received) < count:
        message = bus.recv(timeout=timeout_s)
        if message is None:
            break
        received.append(message)
    return received
