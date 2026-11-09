"""Cyclic E2E-protected sender with fault injection, and the matching receiver."""

from dataclasses import dataclass, field
from enum import StrEnum

from atep.bench.e2e import E2EChecker, E2EConfig, E2EProtector, E2EStatus
from atep.bench.vector_trace import TraceFrame


class CyclicFault(StrEnum):
    DROP = "drop"
    CORRUPT_CRC = "corrupt_crc"
    REPEAT_COUNTER = "repeat_counter"
    SKIP_COUNTERS = "skip_counters"


@dataclass
class CyclicSender:
    """Sends an E2E-protected frame every period. Faults apply to chosen cycle numbers."""

    arbitration_id: int
    period_us: int
    e2e: E2EConfig
    stop_after_us: int | None = None
    faults: dict[int, CyclicFault] = field(default_factory=dict)
    is_extended_id: bool = False
    cycle: int = 0
    _protector: E2EProtector | None = None
    _last: bytes = b""

    def __post_init__(self) -> None:
        if self.period_us <= 0:
            raise ValueError("period must be positive")
        self._protector = E2EProtector(self.e2e)

    def _payload(self) -> bytes:
        value = (self.cycle * 7) & 0xFF
        data = bytearray(self.e2e.length)
        for index in range(len(data)):
            if index not in {self.e2e.crc_byte, self.e2e.counter_byte}:
                data[index] = value
        return bytes(data)

    def _next_time(self) -> int:
        return self.cycle * self.period_us

    def _frame(self, now_us: int) -> TraceFrame | None:
        assert self._protector is not None
        fault = self.faults.get(self.cycle)
        if fault is CyclicFault.REPEAT_COUNTER and self._last:
            data = self._last
        else:
            if fault is CyclicFault.SKIP_COUNTERS:
                self._protector.counter = (self._protector.counter + 3) % 15
            data = self._protector.protect(self._payload())
        self._last = data
        if fault is CyclicFault.DROP:
            return None
        if fault is CyclicFault.CORRUPT_CRC:
            corrupted = bytearray(data)
            corrupted[self.e2e.crc_byte] ^= 0xFF
            data = bytes(corrupted)
        return TraceFrame(now_us, self.arbitration_id, self.is_extended_id, data)

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        return []

    def poll(self, now_us: int) -> list[TraceFrame]:
        frames: list[TraceFrame] = []
        while self.next_deadline_us() is not None and self._next_time() <= now_us:
            frame = self._frame(self._next_time())
            self.cycle += 1
            if frame is not None:
                frames.append(frame)
        return frames

    def next_deadline_us(self) -> int | None:
        upcoming = self._next_time()
        if self.stop_after_us is not None and upcoming > self.stop_after_us:
            return None
        return upcoming


@dataclass(frozen=True)
class E2ERecord:
    at_us: int
    status: E2EStatus


@dataclass
class E2EReceiver:
    """Checks every frame on one identifier and keeps the status history."""

    arbitration_id: int
    e2e: E2EConfig
    is_extended_id: bool = False
    records: list[E2ERecord] = field(default_factory=list)
    _checker: E2EChecker | None = None

    def __post_init__(self) -> None:
        self._checker = E2EChecker(self.e2e)

    def statuses(self) -> list[E2EStatus]:
        return [record.status for record in self.records]

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        assert self._checker is not None
        if (frame.arbitration_id, frame.is_extended_id) == (
            self.arbitration_id,
            self.is_extended_id,
        ):
            self.records.append(E2ERecord(now_us, self._checker.check(frame.data)))
        return []

    def poll(self, now_us: int) -> list[TraceFrame]:
        return []

    def next_deadline_us(self) -> int | None:
        return None
