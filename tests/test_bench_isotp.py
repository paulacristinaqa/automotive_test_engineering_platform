import pytest

from atep.bench.isotp import (
    IsoTpConfig,
    IsoTpEndpoint,
    IsoTpErrorCode,
    IsoTpEvent,
    IsoTpEventKind,
    decode_st_min,
    encode_st_min,
)
from atep.bench.link import SimulatedLink
from atep.bench.vector_trace import TraceFrame

TESTER = IsoTpConfig(tx_id=0x7E0, rx_id=0x7E8)


def _ecu(**overrides: object) -> IsoTpConfig:
    values: dict[str, object] = {"tx_id": 0x7E8, "rx_id": 0x7E0}
    return IsoTpConfig(**(values | overrides))  # type: ignore[arg-type]


def _events(endpoint: IsoTpEndpoint) -> list[IsoTpEvent]:
    events = list(endpoint.events)
    endpoint.events.clear()
    return events


def _transfer(
    sender: IsoTpEndpoint, receiver: IsoTpEndpoint, payload: bytes
) -> tuple[list[TraceFrame], bytes]:
    """Run both endpoints on a simulated bus until the receiver completes or fails."""
    link = SimulatedLink([sender, receiver])
    link.submit(sender, sender.send(payload, 0))

    def finished() -> bool:
        return any(
            e.kind in {IsoTpEventKind.RX_COMPLETE, IsoTpEventKind.ERROR} for e in receiver.events
        )

    link.run_until(finished)
    complete = [e for e in receiver.events if e.kind is IsoTpEventKind.RX_COMPLETE]
    return link.trace, complete[-1].payload if complete else b""


def test_single_frame_is_padded_and_completes_immediately() -> None:
    sender = IsoTpEndpoint(TESTER)
    frames = sender.send(b"\x22\xf1\x90", 100)
    assert [f.data.hex() for f in frames] == ["0322f190cccccccc"]
    assert [e.kind for e in _events(sender)] == [IsoTpEventKind.TX_COMPLETE]
    receiver = IsoTpEndpoint(_ecu())
    assert receiver.on_frame(frames[0], 100) == []
    assert _events(receiver)[0].payload == b"\x22\xf1\x90"


def test_frames_on_other_identifiers_are_ignored() -> None:
    receiver = IsoTpEndpoint(_ecu())
    assert receiver.on_frame(TraceFrame(0, 0x123, False, b"\x02\x10\x03"), 0) == []
    assert receiver.on_frame(TraceFrame(0, 0x7E0, True, b"\x02\x10\x03"), 0) == []
    assert not receiver.events


def test_multi_frame_transfer_respects_block_size_and_st_min() -> None:
    payload = bytes(range(40))
    sender = IsoTpEndpoint(TESTER)
    receiver = IsoTpEndpoint(_ecu(block_size=4, st_min_us=2_000))
    log, received = _transfer(sender, receiver, payload)
    assert received == payload
    kinds = [(f.arbitration_id, f.data[0] >> 4) for f in log]
    # FF, FC, 4 CFs, FC, last CF.
    assert kinds == [(0x7E0, 1), (0x7E8, 3)] + [(0x7E0, 2)] * 4 + [(0x7E8, 3), (0x7E0, 2)]
    flow_control = log[1].data
    assert flow_control[:3] == bytes([0x30, 4, 2])
    cf_times = [f.timestamp_us for f in log if f.arbitration_id == 0x7E0 and f.data[0] >> 4 == 2]
    assert cf_times[1] - cf_times[0] == 2_000
    assert [f.data[0] & 0x0F for f in log if f.data[0] >> 4 == 2] == [1, 2, 3, 4, 5]


def test_sequence_number_wraps_after_fifteen() -> None:
    payload = bytes(index % 256 for index in range(200))
    sender = IsoTpEndpoint(TESTER)
    receiver = IsoTpEndpoint(_ecu())
    log, received = _transfer(sender, receiver, payload)
    assert received == payload
    numbers = [f.data[0] & 0x0F for f in log if f.data[0] >> 4 == 2]
    assert numbers[14:17] == [15, 0, 1]


def test_can_fd_uses_escape_single_frame_and_large_frames() -> None:
    tester = IsoTpConfig(tx_id=0x7E0, rx_id=0x7E8, fd=True, tx_data_length=64)
    ecu = _ecu(fd=True, tx_data_length=64)
    sender = IsoTpEndpoint(tester)
    frame = sender.send(bytes(range(20)), 0)[0]
    assert frame.is_fd and frame.data[:2] == bytes([0x00, 20]) and len(frame.data) == 24
    receiver = IsoTpEndpoint(ecu)
    receiver.on_frame(frame, 0)
    assert receiver.events[-1].payload == bytes(range(20))

    payload = bytes(index % 256 for index in range(300))
    log, received = _transfer(IsoTpEndpoint(tester), IsoTpEndpoint(ecu), payload)
    assert received == payload
    assert len(log[0].data) == 64


def test_flow_control_wait_and_wait_limit() -> None:
    sender = IsoTpEndpoint(IsoTpConfig(tx_id=0x7E0, rx_id=0x7E8, max_wait_frames=1))
    receiver = IsoTpEndpoint(_ecu(wait_frames_before_cts=1))
    _, received = _transfer(sender, receiver, bytes(30))
    assert received == bytes(30)

    # The default sender accepts no WAIT frame at all.
    strict = IsoTpEndpoint(TESTER)
    ff = strict.send(bytes(30), 0)[0]
    for reply in IsoTpEndpoint(_ecu(wait_frames_before_cts=1)).on_frame(ff, 0):
        strict.on_frame(reply, 0)
    assert strict.events[-1].error is IsoTpErrorCode.WAIT_LIMIT_EXCEEDED
    assert not strict.busy


def test_overflow_flow_control_aborts_sender() -> None:
    sender = IsoTpEndpoint(TESTER)
    receiver = IsoTpEndpoint(_ecu(max_message_length=16))
    ff = sender.send(bytes(40), 0)[0]
    replies = receiver.on_frame(ff, 0)
    assert replies[0].data[0] == 0x32
    assert receiver.events[-1].error is IsoTpErrorCode.BUFFER_OVERFLOW
    sender.on_frame(replies[0], 0)
    assert sender.events[-1].error is IsoTpErrorCode.BUFFER_OVERFLOW
    assert not sender.busy


def test_n_bs_timeout_when_no_flow_control_arrives() -> None:
    sender = IsoTpEndpoint(IsoTpConfig(tx_id=0x7E0, rx_id=0x7E8, n_bs_timeout_us=1_000))
    sender.send(bytes(20), 0)
    assert sender.next_deadline_us() == 1_000
    sender.poll(999)
    assert sender.busy
    sender.poll(1_000)
    assert sender.events[-1] == IsoTpEvent(
        IsoTpEventKind.ERROR, 1_000, error=IsoTpErrorCode.N_BS_TIMEOUT
    )


def test_n_cr_timeout_and_wrong_sequence_number() -> None:
    receiver = IsoTpEndpoint(_ecu(n_cr_timeout_us=500))
    ff = IsoTpEndpoint(TESTER).send(bytes(20), 0)[0]
    receiver.on_frame(ff, 0)
    receiver.poll(500)
    assert receiver.events[-1].error is IsoTpErrorCode.N_CR_TIMEOUT

    receiver = IsoTpEndpoint(_ecu())
    receiver.on_frame(ff, 0)
    receiver.on_frame(TraceFrame(10, 0x7E0, False, bytes([0x22]) + bytes(7)), 10)
    assert receiver.events[-1].error is IsoTpErrorCode.WRONG_SEQUENCE_NUMBER


def test_new_single_frame_interrupts_a_reception() -> None:
    receiver = IsoTpEndpoint(_ecu())
    receiver.on_frame(IsoTpEndpoint(TESTER).send(bytes(20), 0)[0], 0)
    receiver.on_frame(TraceFrame(5, 0x7E0, False, b"\x02\x3e\x00"), 5)
    kinds = [(e.kind, e.error) for e in receiver.events]
    assert kinds[-2:] == [
        (IsoTpEventKind.ERROR, IsoTpErrorCode.UNEXPECTED_PDU),
        (IsoTpEventKind.RX_COMPLETE, None),
    ]


def test_invalid_frames_are_reported() -> None:
    receiver = IsoTpEndpoint(_ecu())
    for data in (b"", b"\x00\x01", b"\x10\x14\x00", b"\x40\x00", b"\x05\x01"):
        receiver.on_frame(TraceFrame(0, 0x7E0, False, data), 0)
    errors = [e.error for e in receiver.events]
    assert errors.count(IsoTpErrorCode.INVALID_FRAME) == 5


@pytest.mark.parametrize(
    ("st_min_us", "encoded"), [(0, 0), (5_000, 5), (127_000, 0x7F), (100, 0xF1), (900, 0xF9)]
)
def test_st_min_encoding(st_min_us: int, encoded: int) -> None:
    assert encode_st_min(st_min_us) == encoded
    assert decode_st_min(encoded) == st_min_us


def test_st_min_reserved_values_mean_maximum() -> None:
    assert decode_st_min(0x80) == 127_000
    assert decode_st_min(0xFA) == 127_000
    with pytest.raises(ValueError):
        encode_st_min(1_500)


@pytest.mark.parametrize(
    "overrides",
    [
        {"rx_id": 0x7E8},
        {"tx_data_length": 12},
        {"fd": True, "tx_data_length": 13},
        {"block_size": 256},
        {"padding": 300},
        {"max_message_length": 5000},
        {"st_min_us": 1_234},
    ],
)
def test_invalid_configurations_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _ecu(**overrides)


def test_send_rejects_bad_payloads_and_overlap() -> None:
    sender = IsoTpEndpoint(TESTER)
    with pytest.raises(ValueError):
        sender.send(b"", 0)
    sender.send(bytes(20), 0)
    with pytest.raises(RuntimeError):
        sender.send(b"\x01", 0)


def test_padding_can_be_disabled() -> None:
    sender = IsoTpEndpoint(IsoTpConfig(tx_id=0x7E0, rx_id=0x7E8, padding=None))
    assert sender.send(b"\x10\x03", 0)[0].data == b"\x02\x10\x03"
