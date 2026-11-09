from uuid import uuid4

import can
import pytest
from pydantic import ValidationError

from atep.bench.bus import (
    BenchBusConfig,
    BenchInterface,
    collect_frames,
    from_message,
    open_bench_bus,
    replay_frames,
)
from atep.bench.vector_trace import TraceFrame

FRAMES = [
    TraceFrame(0, 0x180, False, bytes([1, 2, 3, 4])),
    TraceFrame(1_500, 0x18FF5010, True, bytes(range(8))),
    TraceFrame(20_000, 0x200, False, bytes(range(16)), is_fd=True, bitrate_switch=True),
]


def _config() -> BenchBusConfig:
    return BenchBusConfig(channel=f"atep-test-{uuid4()}", fd=True, data_bitrate_kbps=2000)


def test_config_defaults_to_virtual_and_rejects_unknown_interfaces() -> None:
    assert BenchBusConfig().interface is BenchInterface.VIRTUAL
    with pytest.raises(ValidationError):
        BenchBusConfig.model_validate({"interface": "kvaser"})
    with pytest.raises(ValidationError, match="data-phase"):
        BenchBusConfig(data_bitrate_kbps=2000)
    with pytest.raises(ValidationError):
        BenchBusConfig.model_validate({"interface": "virtual", "extra": 1})


def test_virtual_bus_carries_classic_extended_and_fd_frames_without_loss() -> None:
    config = _config()
    sender, receiver = open_bench_bus(config), open_bench_bus(config)
    try:
        assert replay_frames(sender, FRAMES) == 3
        received = [from_message(m) for m in collect_frames(receiver, count=3, timeout_s=1.0)]
    finally:
        sender.shutdown()
        receiver.shutdown()
    assert [
        (f.arbitration_id, f.is_extended_id, f.is_fd, f.bitrate_switch, f.data) for f in received
    ] == [(f.arbitration_id, f.is_extended_id, f.is_fd, f.bitrate_switch, f.data) for f in FRAMES]


def test_realtime_replay_waits_for_each_logical_timestamp() -> None:
    now = [100.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(round(seconds, 6))
        now[0] += seconds

    sent: list[int] = []

    class RecordingBus:
        def send(self, message: can.Message) -> None:
            sent.append(message.arbitration_id)

    count = replay_frames(
        RecordingBus(),  # type: ignore[arg-type]
        reversed(FRAMES),
        realtime=True,
        clock=lambda: now[0],
        sleep=sleep,
    )
    assert count == 3
    assert sent == [0x180, 0x18FF5010, 0x200]
    assert sleeps == [0.0015, 0.0185]


def test_deterministic_replay_never_sleeps() -> None:
    class NullBus:
        def send(self, message: can.Message) -> None:
            return None

    def forbidden(_: float) -> None:
        raise AssertionError("deterministic replay must not sleep")

    assert replay_frames(NullBus(), FRAMES, sleep=forbidden) == 3  # type: ignore[arg-type]


def test_collect_stops_when_the_bus_is_quiet() -> None:
    bus = open_bench_bus(_config())
    try:
        assert collect_frames(bus, count=5, timeout_s=0.01) == []
    finally:
        bus.shutdown()


def test_from_message_maps_channels_and_timestamps() -> None:
    message = can.Message(
        timestamp=10.000002, arbitration_id=0x10, data=b"\x01", channel=1, is_extended_id=False
    )
    frame = from_message(message, start_s=10.0)
    assert (frame.timestamp_us, frame.channel) == (2, 2)
    named = can.Message(timestamp=1.0, arbitration_id=0x10, channel="vcan0", is_extended_id=False)
    assert from_message(named, start_s=5.0) == TraceFrame(0, 0x10, False, b"", channel=1)
