"""UDS (ISO 14229) tester over ISO-TP, with P2 and P2* response timing."""

from dataclasses import dataclass
from enum import IntEnum, StrEnum

from atep.bench.isotp import IsoTpConfig, IsoTpEndpoint, IsoTpErrorCode, IsoTpEventKind
from atep.bench.vector_trace import TraceFrame

NEGATIVE_RESPONSE = 0x7F
POSITIVE_OFFSET = 0x40
SUPPRESS_POSITIVE_RESPONSE = 0x80
# Only these services carry a sub-function byte whose bit 7 suppresses the positive response.
SERVICES_WITH_SUBFUNCTION = frozenset({0x10, 0x11, 0x19, 0x27, 0x28, 0x31, 0x3E, 0x85, 0x87})


def suppresses_positive_response(request: bytes) -> bool:
    return (
        len(request) >= 2
        and request[0] in SERVICES_WITH_SUBFUNCTION
        and bool(request[1] & SUPPRESS_POSITIVE_RESPONSE)
    )


class Nrc(IntEnum):
    """Negative response codes used by the bench."""

    SERVICE_NOT_SUPPORTED = 0x11
    SUBFUNCTION_NOT_SUPPORTED = 0x12
    INCORRECT_MESSAGE_LENGTH = 0x13
    CONDITIONS_NOT_CORRECT = 0x22
    REQUEST_SEQUENCE_ERROR = 0x24
    REQUEST_OUT_OF_RANGE = 0x31
    SECURITY_ACCESS_DENIED = 0x33
    INVALID_KEY = 0x35
    EXCEEDED_NUMBER_OF_ATTEMPTS = 0x36
    REQUIRED_TIME_DELAY_NOT_EXPIRED = 0x37
    RESPONSE_PENDING = 0x78
    SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION = 0x7F


class UdsOutcome(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NO_RESPONSE_EXPECTED = "no_response_expected"
    P2_TIMEOUT = "p2_timeout"
    P2_STAR_TIMEOUT = "p2_star_timeout"
    TRANSPORT_ERROR = "transport_error"
    UNEXPECTED_RESPONSE = "unexpected_response"


@dataclass(frozen=True)
class UdsResult:
    request: bytes
    outcome: UdsOutcome
    response: bytes = b""
    nrc: int | None = None
    pending_count: int = 0
    sent_at_us: int = 0
    completed_at_us: int = 0
    transport_error: IsoTpErrorCode | None = None

    @property
    def response_time_us(self) -> int:
        return self.completed_at_us - self.sent_at_us


def physical_addressing(*, tester_id: int = 0x7E0, ecu_id: int = 0x7E8) -> IsoTpConfig:
    """Typical 11-bit physical diagnostic IDs: tester 0x7E0, ECU response 0x7E8."""
    return IsoTpConfig(tx_id=tester_id, rx_id=ecu_id)


class UdsClient:
    """Sends one request at a time and classifies the response.

    P2 runs from the end of the request transmission to the start of the
    response. Each 0x78 response-pending answer restarts the wait with P2*.
    """

    def __init__(
        self,
        config: IsoTpConfig,
        *,
        p2_us: int = 50_000,
        p2_star_us: int = 5_000_000,
    ) -> None:
        self.transport = IsoTpEndpoint(config)
        self.p2_us = p2_us
        self.p2_star_us = p2_star_us
        self.results: list[UdsResult] = []
        self._request: bytes | None = None
        self._sent_at = 0
        self._deadline: int | None = None
        self._deadline_kind = UdsOutcome.P2_TIMEOUT
        self._pending = 0

    @property
    def idle(self) -> bool:
        return self._request is None

    @property
    def last(self) -> UdsResult:
        return self.results[-1]

    def request(self, payload: bytes, now_us: int) -> list[TraceFrame]:
        if self._request is not None:
            raise RuntimeError("a request is already in progress")
        self._request = bytes(payload)
        self._sent_at = now_us
        self._deadline = None
        self._pending = 0
        frames = self.transport.send(self._request, now_us)
        self._drain(now_us)
        return frames

    def _finish(
        self,
        outcome: UdsOutcome,
        now_us: int,
        *,
        response: bytes = b"",
        nrc: int | None = None,
        transport_error: IsoTpErrorCode | None = None,
    ) -> None:
        assert self._request is not None
        self.results.append(
            UdsResult(
                request=self._request,
                outcome=outcome,
                response=response,
                nrc=nrc,
                pending_count=self._pending,
                sent_at_us=self._sent_at,
                completed_at_us=now_us,
                transport_error=transport_error,
            )
        )
        self._request = None
        self._deadline = None

    def _suppressed(self) -> bool:
        return suppresses_positive_response(self._request or b"")

    def _classify(self, response: bytes, now_us: int) -> None:
        request = self._request
        assert request is not None
        sid = request[0]
        if len(response) >= 3 and response[0] == NEGATIVE_RESPONSE and response[1] == sid:
            if response[2] == Nrc.RESPONSE_PENDING:
                self._pending += 1
                self._deadline = now_us + self.p2_star_us
                self._deadline_kind = UdsOutcome.P2_STAR_TIMEOUT
                return
            self._finish(UdsOutcome.NEGATIVE, now_us, response=response, nrc=response[2])
            return
        if response and response[0] == sid + POSITIVE_OFFSET:
            self._finish(UdsOutcome.POSITIVE, now_us, response=response)
            return
        self._finish(UdsOutcome.UNEXPECTED_RESPONSE, now_us, response=response)

    def _drain(self, now_us: int) -> None:
        while self.transport.events:
            event = self.transport.events.popleft()
            if self._request is None:
                continue
            if event.kind is IsoTpEventKind.TX_COMPLETE:
                if self._suppressed():
                    # Only negative responses may still arrive; give them P2 to show up.
                    self._deadline = event.at_us + self.p2_us
                    self._deadline_kind = UdsOutcome.NO_RESPONSE_EXPECTED
                else:
                    self._deadline = event.at_us + self.p2_us
                    self._deadline_kind = UdsOutcome.P2_TIMEOUT
            elif event.kind is IsoTpEventKind.RX_STARTED:
                # The transport's N_Cr timer now guards the rest of the response.
                self._deadline = None
            elif event.kind is IsoTpEventKind.RX_COMPLETE:
                self._classify(event.payload, event.at_us)
            elif event.kind is IsoTpEventKind.ERROR:
                self._finish(UdsOutcome.TRANSPORT_ERROR, event.at_us, transport_error=event.error)

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        frames = self.transport.on_frame(frame, now_us)
        self._drain(now_us)
        return frames

    def poll(self, now_us: int) -> list[TraceFrame]:
        frames = self.transport.poll(now_us)
        self._drain(now_us)
        if self._request is not None and self._deadline is not None and now_us >= self._deadline:
            self._finish(self._deadline_kind, self._deadline)
        return frames

    def next_deadline_us(self) -> int | None:
        values = [
            item for item in (self._deadline, self.transport.next_deadline_us()) if item is not None
        ]
        return min(values) if values else None
