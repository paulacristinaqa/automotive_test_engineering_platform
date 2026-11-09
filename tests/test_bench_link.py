from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from atep.bench.bus import BenchBusConfig, open_bench_bus
from atep.bench.cyclic import CyclicSender
from atep.bench.e2e import E2EConfig
from atep.bench.isotp import IsoTpConfig
from atep.bench.link import BusNodeRunner, SimulatedLink, classic_frame_time_us
from atep.bench.uds import UdsClient, UdsOutcome, physical_addressing
from atep.bench.vector_trace import TraceFrame
from atep.bench.virtual_ecu import VirtualEcu


@dataclass
class Burst:
    frames: list[TraceFrame]
    received: list[tuple[int, int]] = field(default_factory=list)
    sent: bool = False

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        self.received.append((frame.arbitration_id, now_us))
        return []

    def poll(self, now_us: int) -> list[TraceFrame]:
        if self.sent:
            return []
        self.sent = True
        return self.frames

    def next_deadline_us(self) -> int | None:
        return None


@dataclass
class Stuck:
    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        return []

    def poll(self, now_us: int) -> list[TraceFrame]:
        return []

    def next_deadline_us(self) -> int | None:
        return 0


def test_frame_time_grows_with_payload_and_identifier_length() -> None:
    empty = classic_frame_time_us(TraceFrame(0, 0x1, False, b""), bitrate_kbps=500)
    full = classic_frame_time_us(TraceFrame(0, 0x1, False, bytes(8)), bitrate_kbps=500)
    extended = classic_frame_time_us(TraceFrame(0, 0x1, True, bytes(8)), bitrate_kbps=500)
    assert empty < full < extended
    assert 250 <= full <= 280
    assert classic_frame_time_us(TraceFrame(0, 0x1, False, bytes(8)), bitrate_kbps=250) > full


def test_frames_queue_behind_each_other_and_reach_every_other_node() -> None:
    frames = [TraceFrame(0, 0x100 + index, False, bytes(8)) for index in range(3)]
    sender, listener = Burst(frames), Burst([])
    link = SimulatedLink([sender, listener])
    link.advance_to(10_000)
    starts = [frame.timestamp_us for frame in link.trace]
    duration = classic_frame_time_us(frames[0], bitrate_kbps=500)
    assert starts == [0, duration, 2 * duration]
    assert listener.received == [(0x100, duration), (0x101, 2 * duration), (0x102, 3 * duration)]
    assert sender.received == []


def test_fd_frames_use_the_data_bitrate() -> None:
    fd = TraceFrame(0, 0x200, False, bytes(64), is_fd=True, bitrate_switch=True)
    slow = SimulatedLink([Burst([fd]), Burst([])], data_bitrate_kbps=1000)
    fast = SimulatedLink([Burst([fd]), Burst([])], data_bitrate_kbps=5000)
    slow.advance_to(5_000)
    fast.advance_to(5_000)
    assert fast.nodes[1].received[0][1] < slow.nodes[1].received[0][1]  # type: ignore[attr-defined]


def test_run_until_reports_limits_and_stale_deadlines() -> None:
    link = SimulatedLink([Burst([])])
    assert link.run_until(lambda: False) is False


def test_run_until_timeout_is_relative_to_the_call() -> None:
    """Regression: the limit used to be absolute, so every call after 60 s gave up at once."""
    sender = CyclicSender(0x101, 1_000_000, E2EConfig(data_id=1, length=8))
    link = SimulatedLink([sender])
    link.advance_to(120_000_000)
    target = link.now_us + 3_000_000
    assert link.run_until(lambda: link.now_us >= target, timeout_us=5_000_000) is True
    start = link.now_us
    assert link.run_until(lambda: False, timeout_us=2_500_000) is False
    assert 2_500_000 <= link.now_us - start <= 3_500_000
    with pytest.raises(RuntimeError, match="no progress"):
        SimulatedLink([Stuck()]).run_until(lambda: False, max_steps=50)
    with pytest.raises(RuntimeError, match="no progress"):
        SimulatedLink([Stuck()]).advance_to(10, max_steps=50)


def test_bus_runner_drives_a_uds_exchange_on_the_virtual_bus() -> None:
    config = BenchBusConfig(channel=f"atep-link-{uuid4()}")
    tester = UdsClient(physical_addressing())
    ecu = VirtualEcu(IsoTpConfig(tx_id=0x7E8, rx_id=0x7E0))
    tester_bus, ecu_bus = open_bench_bus(config), open_bench_bus(config)
    try:
        tester_runner = BusNodeRunner(tester_bus, tester)
        ecu_runner = BusNodeRunner(ecu_bus, ecu)
        tester_runner.send(tester.request(bytes.fromhex("22F190"), tester_runner.now_us()))
        for _ in range(2000):
            if tester.idle:
                break
            ecu_runner.step(timeout_s=0.001)
            tester_runner.step(timeout_s=0.001)
    finally:
        tester_bus.shutdown()
        ecu_bus.shutdown()
    assert tester.last.outcome is UdsOutcome.POSITIVE
    assert tester.last.response.startswith(b"\x62\xf1\x90WATEP")
    assert [frame.data[0] >> 4 for frame in ecu_runner.sent] == [1, 2, 2]
