"""ISO-TP (ISO 15765-2) transport for the bench, without I/O.

The endpoint never reads a clock or touches a bus. Callers pass the current
logical time in microseconds and send the frames the endpoint returns. That keeps
segmentation, flow control and timeouts deterministic and testable.
"""

from collections import deque
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from atep.bench.vector_trace import TraceFrame
from atep.can_network.schemas import CAN_FD_PAYLOAD_LENGTHS

MAX_MESSAGE_LENGTH = 4095


class FlowStatus(IntEnum):
    CONTINUE_TO_SEND = 0
    WAIT = 1
    OVERFLOW = 2


class IsoTpEventKind(StrEnum):
    TX_COMPLETE = "tx_complete"
    RX_STARTED = "rx_started"
    RX_COMPLETE = "rx_complete"
    ERROR = "error"


class IsoTpErrorCode(StrEnum):
    N_BS_TIMEOUT = "n_bs_timeout"
    N_CR_TIMEOUT = "n_cr_timeout"
    WRONG_SEQUENCE_NUMBER = "wrong_sequence_number"
    UNEXPECTED_PDU = "unexpected_pdu"
    BUFFER_OVERFLOW = "buffer_overflow"
    WAIT_LIMIT_EXCEEDED = "wait_limit_exceeded"
    INVALID_FRAME = "invalid_frame"


@dataclass(frozen=True)
class IsoTpEvent:
    kind: IsoTpEventKind
    at_us: int
    payload: bytes = b""
    error: IsoTpErrorCode | None = None


@dataclass(frozen=True)
class IsoTpConfig:
    """One direction pair: frames go out on `tx_id`, come in on `rx_id`."""

    tx_id: int
    rx_id: int
    is_extended_id: bool = False
    fd: bool = False
    tx_data_length: int = 8
    block_size: int = 0
    st_min_us: int = 0
    padding: int | None = 0xCC
    max_message_length: int = MAX_MESSAGE_LENGTH
    n_bs_timeout_us: int = 1_000_000
    n_cr_timeout_us: int = 1_000_000
    max_wait_frames: int = 0
    wait_frames_before_cts: int = 0

    def __post_init__(self) -> None:
        if self.tx_id == self.rx_id:
            raise ValueError("transmit and receive identifiers must differ")
        if self.fd:
            if self.tx_data_length not in CAN_FD_PAYLOAD_LENGTHS or self.tx_data_length < 8:
                raise ValueError("CAN FD transport needs a valid frame length of at least 8")
        elif self.tx_data_length != 8:
            raise ValueError("classic CAN transport uses 8-byte frames")
        if not 0 <= self.block_size <= 255:
            raise ValueError("block size must fit in one byte")
        if self.padding is not None and not 0 <= self.padding <= 255:
            raise ValueError("padding must be a byte value")
        if not 1 <= self.max_message_length <= MAX_MESSAGE_LENGTH:
            raise ValueError(f"message length is limited to {MAX_MESSAGE_LENGTH} bytes")
        encode_st_min(self.st_min_us)


def encode_st_min(st_min_us: int) -> int:
    """STmin byte: 0x00-0x7F milliseconds, 0xF1-0xF9 hundreds of microseconds."""
    if st_min_us == 0:
        return 0
    if st_min_us % 1000 == 0 and st_min_us // 1000 <= 0x7F:
        return st_min_us // 1000
    if st_min_us % 100 == 0 and 1 <= st_min_us // 100 <= 9:
        return 0xF0 + st_min_us // 100
    raise ValueError("STmin must be 100-900 µs in 100 µs steps or 0-127 ms in 1 ms steps")


def decode_st_min(value: int) -> int:
    if value <= 0x7F:
        return value * 1000
    if 0xF1 <= value <= 0xF9:
        return (value - 0xF0) * 100
    # Reserved values must be treated as the maximum, 127 ms.
    return 127_000


def _frame_length(length: int, *, fd: bool) -> int:
    if not fd:
        return 8
    return min(item for item in CAN_FD_PAYLOAD_LENGTHS if item >= length)


@dataclass
class _Transmission:
    payload: bytes
    offset: int
    sequence: int
    block_remaining: int
    st_min_us: int
    next_cf_at: int | None
    fc_deadline: int | None
    waits: int


@dataclass
class _Reception:
    length: int
    data: bytearray
    sequence: int
    block_remaining: int
    deadline: int


class IsoTpEndpoint:
    """Sans-IO ISO-TP endpoint: one transmission and one reception at a time."""

    def __init__(self, config: IsoTpConfig) -> None:
        self.config = config
        self.events: deque[IsoTpEvent] = deque()
        self._tx: _Transmission | None = None
        self._rx: _Reception | None = None

    @property
    def busy(self) -> bool:
        return self._tx is not None

    def _frame(self, data: bytes, now_us: int) -> TraceFrame:
        size = _frame_length(len(data), fd=self.config.fd)
        if self.config.padding is not None:
            data = data + bytes([self.config.padding]) * (size - len(data))
        elif self.config.fd and len(data) not in CAN_FD_PAYLOAD_LENGTHS:
            data = data + bytes(size - len(data))
        return TraceFrame(
            timestamp_us=now_us,
            arbitration_id=self.config.tx_id,
            is_extended_id=self.config.is_extended_id,
            data=data,
            is_fd=self.config.fd,
            bitrate_switch=self.config.fd,
        )

    def _error(self, code: IsoTpErrorCode, now_us: int) -> None:
        self.events.append(IsoTpEvent(IsoTpEventKind.ERROR, now_us, error=code))

    # Sending -----------------------------------------------------------------

    def send(self, payload: bytes, now_us: int) -> list[TraceFrame]:
        if self._tx is not None:
            raise RuntimeError("a transmission is already in progress")
        if not 1 <= len(payload) <= self.config.max_message_length:
            raise ValueError("payload length is outside the transport limit")
        dl = self.config.tx_data_length
        if len(payload) <= 7:
            self.events.append(IsoTpEvent(IsoTpEventKind.TX_COMPLETE, now_us))
            return [self._frame(bytes([len(payload)]) + payload, now_us)]
        if dl > 8 and len(payload) <= dl - 2:
            self.events.append(IsoTpEvent(IsoTpEventKind.TX_COMPLETE, now_us))
            return [self._frame(bytes([0x00, len(payload)]) + payload, now_us)]
        first = dl - 2
        header = bytes([0x10 | (len(payload) >> 8), len(payload) & 0xFF])
        self._tx = _Transmission(
            payload=payload,
            offset=first,
            sequence=1,
            block_remaining=0,
            st_min_us=0,
            next_cf_at=None,
            fc_deadline=now_us + self.config.n_bs_timeout_us,
            waits=0,
        )
        return [self._frame(header + payload[:first], now_us)]

    def _consecutive_frames(self, now_us: int) -> list[TraceFrame]:
        tx = self._tx
        frames: list[TraceFrame] = []
        if tx is None:
            return frames
        chunk = self.config.tx_data_length - 1
        while tx.next_cf_at is not None and tx.next_cf_at <= now_us:
            at = tx.next_cf_at
            data = tx.payload[tx.offset : tx.offset + chunk]
            frames.append(self._frame(bytes([0x20 | tx.sequence]) + data, at))
            tx.offset += len(data)
            tx.sequence = (tx.sequence + 1) & 0x0F
            if tx.offset >= len(tx.payload):
                self._tx = None
                self.events.append(IsoTpEvent(IsoTpEventKind.TX_COMPLETE, at))
                break
            if tx.block_remaining:
                tx.block_remaining -= 1
                if tx.block_remaining == 0:
                    tx.next_cf_at = None
                    tx.fc_deadline = at + self.config.n_bs_timeout_us
                    break
            tx.next_cf_at = at + tx.st_min_us
        return frames

    def _on_flow_control(self, data: bytes, now_us: int) -> list[TraceFrame]:
        tx = self._tx
        if tx is None or tx.fc_deadline is None or len(data) < 3:
            return []
        status = data[0] & 0x0F
        if status == FlowStatus.OVERFLOW:
            self._tx = None
            self._error(IsoTpErrorCode.BUFFER_OVERFLOW, now_us)
            return []
        if status == FlowStatus.WAIT:
            tx.waits += 1
            if tx.waits > self.config.max_wait_frames:
                self._tx = None
                self._error(IsoTpErrorCode.WAIT_LIMIT_EXCEEDED, now_us)
                return []
            tx.fc_deadline = now_us + self.config.n_bs_timeout_us
            return []
        if status != FlowStatus.CONTINUE_TO_SEND:
            self._tx = None
            self._error(IsoTpErrorCode.INVALID_FRAME, now_us)
            return []
        tx.block_remaining = data[1]
        tx.st_min_us = decode_st_min(data[2])
        tx.fc_deadline = None
        tx.waits = 0
        tx.next_cf_at = now_us
        return self._consecutive_frames(now_us)

    # Receiving ---------------------------------------------------------------

    def _flow_control(self, status: FlowStatus, now_us: int) -> TraceFrame:
        data = bytes([0x30 | status, self.config.block_size, encode_st_min(self.config.st_min_us)])
        return self._frame(data, now_us)

    def _start_reception(self, length: int, data: bytes, now_us: int) -> list[TraceFrame]:
        if self._rx is not None:
            self._error(IsoTpErrorCode.UNEXPECTED_PDU, now_us)
            self._rx = None
        if length > self.config.max_message_length:
            self._error(IsoTpErrorCode.BUFFER_OVERFLOW, now_us)
            return [self._flow_control(FlowStatus.OVERFLOW, now_us)]
        self._rx = _Reception(
            length=length,
            data=bytearray(data[:length]),
            sequence=1,
            block_remaining=self.config.block_size,
            deadline=now_us + self.config.n_cr_timeout_us,
        )
        self.events.append(IsoTpEvent(IsoTpEventKind.RX_STARTED, now_us))
        # Optional WAIT frames let tests exercise the sender's N_Bs and WFTmax handling.
        frames = [
            self._flow_control(FlowStatus.WAIT, now_us)
            for _ in range(self.config.wait_frames_before_cts)
        ]
        frames.append(self._flow_control(FlowStatus.CONTINUE_TO_SEND, now_us))
        return frames

    def _single(self, length: int, data: bytes, now_us: int) -> None:
        if self._rx is not None:
            self._error(IsoTpErrorCode.UNEXPECTED_PDU, now_us)
            self._rx = None
        if length == 0 or length > len(data):
            self._error(IsoTpErrorCode.INVALID_FRAME, now_us)
            return
        self.events.append(IsoTpEvent(IsoTpEventKind.RX_COMPLETE, now_us, payload=data[:length]))

    def _consecutive(self, data: bytes, sequence: int, now_us: int) -> list[TraceFrame]:
        rx = self._rx
        if rx is None:
            return []
        if sequence != rx.sequence:
            self._rx = None
            self._error(IsoTpErrorCode.WRONG_SEQUENCE_NUMBER, now_us)
            return []
        rx.data.extend(data[: rx.length - len(rx.data)])
        rx.sequence = (rx.sequence + 1) & 0x0F
        if len(rx.data) >= rx.length:
            self._rx = None
            payload = bytes(rx.data)
            self.events.append(IsoTpEvent(IsoTpEventKind.RX_COMPLETE, now_us, payload=payload))
            return []
        rx.deadline = now_us + self.config.n_cr_timeout_us
        if self.config.block_size:
            rx.block_remaining -= 1
            if rx.block_remaining == 0:
                rx.block_remaining = self.config.block_size
                return [self._flow_control(FlowStatus.CONTINUE_TO_SEND, now_us)]
        return []

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        """Handle a received frame; ignores other identifiers."""
        if frame.arbitration_id != self.config.rx_id:
            return []
        if frame.is_extended_id != self.config.is_extended_id:
            return []
        data = frame.data
        if not data:
            self._error(IsoTpErrorCode.INVALID_FRAME, now_us)
            return []
        kind = data[0] >> 4
        if kind == 0:
            if data[0] & 0x0F:
                self._single(data[0] & 0x0F, data[1:], now_us)
            elif len(data) > 8:
                self._single(data[1], data[2:], now_us)
            else:
                self._error(IsoTpErrorCode.INVALID_FRAME, now_us)
            return []
        if kind == 1:
            if len(data) < 8:
                self._error(IsoTpErrorCode.INVALID_FRAME, now_us)
                return []
            length = ((data[0] & 0x0F) << 8) | data[1]
            return self._start_reception(length, data[2:], now_us)
        if kind == 2:
            return self._consecutive(data[1:], data[0] & 0x0F, now_us)
        if kind == 3:
            return self._on_flow_control(data, now_us)
        self._error(IsoTpErrorCode.INVALID_FRAME, now_us)
        return []

    # Time --------------------------------------------------------------------

    def next_deadline_us(self) -> int | None:
        deadlines: list[int] = []
        if self._tx is not None:
            for value in (self._tx.next_cf_at, self._tx.fc_deadline):
                if value is not None:
                    deadlines.append(value)
        if self._rx is not None:
            deadlines.append(self._rx.deadline)
        return min(deadlines) if deadlines else None

    def poll(self, now_us: int) -> list[TraceFrame]:
        """Send due consecutive frames and expire timers."""
        frames = self._consecutive_frames(now_us)
        tx = self._tx
        if tx is not None and tx.fc_deadline is not None and now_us >= tx.fc_deadline:
            self._tx = None
            self._error(IsoTpErrorCode.N_BS_TIMEOUT, tx.fc_deadline)
        rx = self._rx
        if rx is not None and now_us >= rx.deadline:
            self._rx = None
            self._error(IsoTpErrorCode.N_CR_TIMEOUT, rx.deadline)
        return frames
