"""Bench nodes and the links that connect them.

`SimulatedLink` runs nodes on logical time with no wall clock, for deterministic
tests and reproducible traces. `BusNodeRunner` drives one node on a python-can
bus with the real clock, so the same node code can run on hardware.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import can

from atep.bench.bus import from_message
from atep.bench.vector_trace import TraceFrame, to_message


class BenchNode(Protocol):
    """A sans-IO participant: it reacts to frames and time, and returns frames to send."""

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]: ...

    def poll(self, now_us: int) -> list[TraceFrame]: ...

    def next_deadline_us(self) -> int | None: ...


def classic_frame_time_us(frame: TraceFrame, *, bitrate_kbps: int) -> int:
    """Approximate time on the wire: 47 overhead bits plus data, plus worst-case stuffing."""
    data_bits = 8 * len(frame.data)
    overhead = 67 if frame.is_extended_id else 47
    stuffable = overhead - 13 + data_bits
    bits = overhead + data_bits + (stuffable - 1) // 4
    return -(-bits * 1000 // bitrate_kbps)


@dataclass
class SimulatedLink:
    """Deterministic shared bus. Frames queue behind each other and reach every other node."""

    nodes: list[BenchNode]
    bitrate_kbps: int = 500
    data_bitrate_kbps: int = 2000
    now_us: int = 0
    trace: list[TraceFrame] = field(default_factory=list)
    _bus_free_at: int = 0
    _in_flight: list[tuple[int, int, int, TraceFrame]] = field(default_factory=list)
    _order: int = 0

    def _frame_time(self, frame: TraceFrame) -> int:
        if not frame.is_fd:
            return classic_frame_time_us(frame, bitrate_kbps=self.bitrate_kbps)
        # Arbitration phase at the nominal rate, data phase at the data rate.
        arbitration = -(-30 * 1000 // self.bitrate_kbps)
        data = -(-(8 * len(frame.data) + 40) * 1000 // self.data_bitrate_kbps)
        return arbitration + data

    def _queue(self, sender: int, frames: list[TraceFrame]) -> None:
        for frame in frames:
            start = max(frame.timestamp_us, self.now_us, self._bus_free_at)
            placed = TraceFrame(
                timestamp_us=start,
                arbitration_id=frame.arbitration_id,
                is_extended_id=frame.is_extended_id,
                data=frame.data,
                is_fd=frame.is_fd,
                bitrate_switch=frame.bitrate_switch,
                channel=frame.channel,
            )
            end = start + self._frame_time(placed)
            self._bus_free_at = end
            self.trace.append(placed)
            self._order += 1
            self._in_flight.append((end, self._order, sender, placed))
        self._in_flight.sort(key=lambda item: (item[0], item[1]))

    def submit(self, sender: BenchNode, frames: list[TraceFrame]) -> None:
        self._queue(self.nodes.index(sender), frames)

    def _next_time(self) -> int | None:
        candidates = [item[0] for item in self._in_flight[:1]]
        candidates.extend(
            deadline for node in self.nodes if (deadline := node.next_deadline_us()) is not None
        )
        return min(candidates) if candidates else None

    def step(self) -> bool:
        """Advance to the next event. Returns False when nothing is left to do."""
        upcoming = self._next_time()
        if upcoming is None:
            return False
        self.now_us = max(self.now_us, upcoming)
        while self._in_flight and self._in_flight[0][0] <= self.now_us:
            end, _, sender, frame = self._in_flight.pop(0)
            for index, node in enumerate(self.nodes):
                if index != sender:
                    self._queue(index, node.on_frame(frame, end))
        for index, node in enumerate(self.nodes):
            self._queue(index, node.poll(self.now_us))
        return True

    def _poll_all(self) -> None:
        """Give every node a chance to act at the current time, even with no deadline."""
        for index, node in enumerate(self.nodes):
            self._queue(index, node.poll(self.now_us))

    def run_until(
        self, done: Callable[[], bool], *, limit_us: int = 60_000_000, max_steps: int = 100_000
    ) -> bool:
        """Step until `done()` is true. Returns False if time ran past `limit_us`."""
        self._poll_all()
        for _ in range(max_steps):
            if done():
                return True
            if not self.step() or self.now_us > limit_us:
                return done()
        raise RuntimeError("simulated link made no progress; a node keeps a stale deadline")

    def advance_to(self, until_us: int, *, max_steps: int = 100_000) -> None:
        """Process every event up to `until_us`, then set the clock there."""
        self._poll_all()
        for _ in range(max_steps):
            upcoming = self._next_time()
            if upcoming is None or upcoming > until_us:
                self.now_us = max(self.now_us, until_us)
                return
            self.step()
        raise RuntimeError("simulated link made no progress; a node keeps a stale deadline")


class BusNodeRunner:
    """Drive one node on a python-can bus using the wall clock."""

    def __init__(
        self,
        bus: can.BusABC,
        node: BenchNode,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.bus = bus
        self.node = node
        self.clock = clock
        self.started = clock()
        self.sent: list[TraceFrame] = []

    def now_us(self) -> int:
        return int((self.clock() - self.started) * 1_000_000)

    def send(self, frames: list[TraceFrame]) -> None:
        for frame in frames:
            self.bus.send(to_message(frame))
            self.sent.append(frame)

    def step(self, *, timeout_s: float = 0.0) -> None:
        message = self.bus.recv(timeout=timeout_s)
        while message is not None:
            frame = from_message(message, start_s=message.timestamp)
            self.send(self.node.on_frame(frame, self.now_us()))
            message = self.bus.recv(timeout=0)
        self.send(self.node.poll(self.now_us()))
