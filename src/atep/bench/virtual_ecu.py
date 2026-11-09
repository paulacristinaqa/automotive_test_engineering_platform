"""A virtual ECU that answers UDS requests over ISO-TP on the bench.

It is a deliberately small diagnostic server: enough behaviour to exercise a
tester the way a system-test bench does (sessions, S3 timeout, security access,
DIDs, DTCs, reset and response pending), all on logical time.
"""

from dataclasses import dataclass, field
from enum import IntEnum

from atep.bench.isotp import IsoTpConfig, IsoTpEndpoint, IsoTpEventKind
from atep.bench.uds import (
    NEGATIVE_RESPONSE,
    POSITIVE_OFFSET,
    Nrc,
    suppresses_positive_response,
)
from atep.bench.vector_trace import TraceFrame

SEED_KEY_MASK = 0x5A5A


class Session(IntEnum):
    DEFAULT = 0x01
    PROGRAMMING = 0x02
    EXTENDED = 0x03


@dataclass
class Dtc:
    code: int
    status: int


@dataclass
class EcuDiagnosticProfile:
    """Static data the virtual ECU serves. Delays model slow services."""

    readable: dict[int, bytes] = field(
        default_factory=lambda: {
            0xF190: b"WATEP000000000001",
            0xF18C: b"SN-0001",
            0xF195: b"XI-2.0",
        }
    )
    writable: set[int] = field(default_factory=lambda: {0xF198})
    slow_dids: dict[int, int] = field(default_factory=dict)
    dtcs: list[Dtc] = field(default_factory=lambda: [Dtc(0x9A0113, 0x2F), Dtc(0xC07300, 0x08)])
    p2_server_us: int = 50_000
    p2_star_server_us: int = 5_000_000
    s3_server_us: int = 5_000_000
    max_key_attempts: int = 3
    lockout_us: int = 10_000_000


def expected_key(seed: bytes) -> bytes:
    """Bench seed/key algorithm: XOR with 0x5A5A. A real ECU keeps this secret."""
    value = int.from_bytes(seed, "big") ^ SEED_KEY_MASK
    return value.to_bytes(len(seed), "big")


class VirtualEcu:
    """Sans-IO UDS server. Implements the BenchNode protocol."""

    def __init__(self, config: IsoTpConfig, profile: EcuDiagnosticProfile | None = None) -> None:
        self.transport = IsoTpEndpoint(config)
        self.profile = profile or EcuDiagnosticProfile()
        self.data = dict(self.profile.readable)
        self.session = Session.DEFAULT
        self.unlocked = False
        self.resets = 0
        self.requests: list[bytes] = []
        self._seed: bytes | None = None
        self._seed_counter = 0x1234
        self._failed_attempts = 0
        self._locked_until = 0
        self._s3_deadline: int | None = None
        self._queue: list[tuple[int, bytes]] = []
        self._pending_until: int | None = None
        self._pending_sid = 0
        self._next_pending_at: int | None = None

    # Session handling --------------------------------------------------------

    def _enter_default(self) -> None:
        self.session = Session.DEFAULT
        self.unlocked = False
        self._seed = None
        self._s3_deadline = None

    def _touch_s3(self, now_us: int) -> None:
        if self.session is not Session.DEFAULT:
            self._s3_deadline = now_us + self.profile.s3_server_us

    # Services ----------------------------------------------------------------

    @staticmethod
    def _negative(sid: int, nrc: Nrc) -> bytes:
        return bytes([NEGATIVE_RESPONSE, sid, nrc])

    def _session_control(self, request: bytes) -> bytes:
        if len(request) != 2:
            return self._negative(0x10, Nrc.INCORRECT_MESSAGE_LENGTH)
        sub = request[1] & 0x7F
        if sub not in {item.value for item in Session}:
            return self._negative(0x10, Nrc.SUBFUNCTION_NOT_SUPPORTED)
        if sub == Session.DEFAULT:
            self._enter_default()
        else:
            self.session = Session(sub)
            self.unlocked = False
            self._seed = None
        p2 = self.profile.p2_server_us // 1000
        p2_star = self.profile.p2_star_server_us // 10_000
        return bytes([0x50, sub]) + p2.to_bytes(2, "big") + p2_star.to_bytes(2, "big")

    def _tester_present(self, request: bytes) -> bytes:
        if len(request) != 2:
            return self._negative(0x3E, Nrc.INCORRECT_MESSAGE_LENGTH)
        if request[1] & 0x7F:
            return self._negative(0x3E, Nrc.SUBFUNCTION_NOT_SUPPORTED)
        return bytes([0x7E, 0x00])

    def _read_did(self, request: bytes) -> bytes:
        if len(request) < 3 or len(request) % 2 == 0:
            return self._negative(0x22, Nrc.INCORRECT_MESSAGE_LENGTH)
        response = bytearray([0x62])
        for index in range(1, len(request), 2):
            did = int.from_bytes(request[index : index + 2], "big")
            if did not in self.data:
                return self._negative(0x22, Nrc.REQUEST_OUT_OF_RANGE)
            response += did.to_bytes(2, "big") + self.data[did]
        return bytes(response)

    def _write_did(self, request: bytes) -> bytes:
        if len(request) < 4:
            return self._negative(0x2E, Nrc.INCORRECT_MESSAGE_LENGTH)
        did = int.from_bytes(request[1:3], "big")
        if did not in self.profile.writable:
            return self._negative(0x2E, Nrc.REQUEST_OUT_OF_RANGE)
        if self.session is Session.DEFAULT:
            return self._negative(0x2E, Nrc.SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION)
        if not self.unlocked:
            return self._negative(0x2E, Nrc.SECURITY_ACCESS_DENIED)
        self.data[did] = bytes(request[3:])
        return bytes([0x6E]) + request[1:3]

    def _security_access(self, request: bytes, now_us: int) -> bytes:
        if len(request) < 2:
            return self._negative(0x27, Nrc.INCORRECT_MESSAGE_LENGTH)
        if self.session is Session.DEFAULT:
            return self._negative(0x27, Nrc.SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION)
        sub = request[1] & 0x7F
        if sub == 0x01:
            if len(request) != 2:
                return self._negative(0x27, Nrc.INCORRECT_MESSAGE_LENGTH)
            if now_us < self._locked_until:
                return self._negative(0x27, Nrc.REQUIRED_TIME_DELAY_NOT_EXPIRED)
            if self.unlocked:
                return bytes([0x67, 0x01, 0x00, 0x00])
            self._seed_counter = (self._seed_counter * 75 + 74) % 0xFFFF or 1
            self._seed = self._seed_counter.to_bytes(2, "big")
            return bytes([0x67, 0x01]) + self._seed
        if sub == 0x02:
            if self._seed is None:
                return self._negative(0x27, Nrc.REQUEST_SEQUENCE_ERROR)
            if len(request) != 2 + len(self._seed):
                return self._negative(0x27, Nrc.INCORRECT_MESSAGE_LENGTH)
            if bytes(request[2:]) != expected_key(self._seed):
                self._failed_attempts += 1
                self._seed = None
                if self._failed_attempts >= self.profile.max_key_attempts:
                    self._failed_attempts = 0
                    self._locked_until = now_us + self.profile.lockout_us
                    return self._negative(0x27, Nrc.EXCEEDED_NUMBER_OF_ATTEMPTS)
                return self._negative(0x27, Nrc.INVALID_KEY)
            self._failed_attempts = 0
            self._seed = None
            self.unlocked = True
            return bytes([0x67, 0x02])
        return self._negative(0x27, Nrc.SUBFUNCTION_NOT_SUPPORTED)

    def _read_dtc(self, request: bytes) -> bytes:
        if len(request) < 2:
            return self._negative(0x19, Nrc.INCORRECT_MESSAGE_LENGTH)
        if request[1] & 0x7F != 0x02:
            return self._negative(0x19, Nrc.SUBFUNCTION_NOT_SUPPORTED)
        if len(request) != 3:
            return self._negative(0x19, Nrc.INCORRECT_MESSAGE_LENGTH)
        mask = request[2]
        response = bytearray([0x59, 0x02, 0xFF])
        for dtc in self.profile.dtcs:
            if dtc.status & mask:
                response += dtc.code.to_bytes(3, "big") + bytes([dtc.status])
        return bytes(response)

    def _clear_dtc(self, request: bytes) -> bytes:
        if len(request) != 4:
            return self._negative(0x14, Nrc.INCORRECT_MESSAGE_LENGTH)
        group = int.from_bytes(request[1:4], "big")
        if group != 0xFFFFFF:
            return self._negative(0x14, Nrc.REQUEST_OUT_OF_RANGE)
        self.profile.dtcs = []
        return bytes([0x54])

    def _reset(self, request: bytes) -> bytes:
        if len(request) != 2:
            return self._negative(0x11, Nrc.INCORRECT_MESSAGE_LENGTH)
        if request[1] & 0x7F != 0x01:
            return self._negative(0x11, Nrc.SUBFUNCTION_NOT_SUPPORTED)
        self.resets += 1
        self._enter_default()
        return bytes([0x51, 0x01])

    def handle(self, request: bytes, now_us: int) -> bytes | None:
        """Return the final response, or None when the positive response is suppressed."""
        if not request:
            return None
        self.requests.append(bytes(request))
        sid = request[0]
        self._touch_s3(now_us)
        if sid == 0x10:
            response = self._session_control(request)
        elif sid == 0x3E:
            response = self._tester_present(request)
        elif sid == 0x22:
            response = self._read_did(request)
        elif sid == 0x2E:
            response = self._write_did(request)
        elif sid == 0x27:
            response = self._security_access(request, now_us)
        elif sid == 0x19:
            response = self._read_dtc(request)
        elif sid == 0x14:
            response = self._clear_dtc(request)
        elif sid == 0x11:
            response = self._reset(request)
        else:
            response = self._negative(sid, Nrc.SERVICE_NOT_SUPPORTED)
        self._touch_s3(now_us)
        if suppresses_positive_response(request) and response[0] == sid + POSITIVE_OFFSET:
            return None
        return response

    # BenchNode ---------------------------------------------------------------

    def _delay_for(self, request: bytes) -> int:
        if request[:1] == b"\x22" and len(request) >= 3:
            return self.profile.slow_dids.get(int.from_bytes(request[1:3], "big"), 0)
        return 0

    def _drain(self, now_us: int) -> list[TraceFrame]:
        frames: list[TraceFrame] = []
        while self.transport.events:
            event = self.transport.events.popleft()
            if event.kind is not IsoTpEventKind.RX_COMPLETE:
                continue
            request = event.payload
            delay = self._delay_for(request)
            response = self.handle(request, event.at_us)
            if response is None:
                continue
            if delay > self.profile.p2_server_us:
                # Answer 0x78 now, repeat it before P2* runs out, then send the result.
                self._pending_sid = request[0]
                self._pending_until = event.at_us + delay
                self._next_pending_at = event.at_us + self.profile.p2_star_server_us // 2
                self._queue.append((event.at_us + delay, response))
                frames += self._send(self._negative(request[0], Nrc.RESPONSE_PENDING), now_us)
            else:
                self._queue.append((event.at_us + delay, response))
        return frames

    def _send(self, payload: bytes, now_us: int) -> list[TraceFrame]:
        if self.transport.busy:
            self._queue.append((now_us, payload))
            return []
        return self.transport.send(payload, now_us)

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        frames = self.transport.on_frame(frame, now_us)
        frames += self._drain(now_us)
        return frames + self.poll(now_us)

    def poll(self, now_us: int) -> list[TraceFrame]:
        frames = self.transport.poll(now_us)
        frames += self._drain(now_us)
        if self._s3_deadline is not None and now_us >= self._s3_deadline:
            self._enter_default()
        if (
            self._pending_until is not None
            and self._next_pending_at is not None
            and now_us >= self._next_pending_at
            and now_us < self._pending_until
        ):
            self._next_pending_at = now_us + self.profile.p2_star_server_us // 2
            frames += self._send(self._negative(self._pending_sid, Nrc.RESPONSE_PENDING), now_us)
        ready = [item for item in self._queue if item[0] <= now_us]
        if ready and not self.transport.busy:
            due, payload = ready[0]
            self._queue.remove((due, payload))
            if self._pending_until is not None and due >= self._pending_until:
                self._pending_until = None
                self._next_pending_at = None
            frames += self.transport.send(payload, now_us)
        return frames

    def next_deadline_us(self) -> int | None:
        pending = None
        if (
            self._pending_until is not None
            and self._next_pending_at is not None
            and self._next_pending_at < self._pending_until
        ):
            pending = self._next_pending_at
        # While the transport is busy, its own timers drive progress; queued answers wait.
        queued = None if self.transport.busy else min((due for due, _ in self._queue), default=None)
        values = [
            item
            for item in (self.transport.next_deadline_us(), self._s3_deadline, pending, queued)
            if item is not None
        ]
        return min(values) if values else None
