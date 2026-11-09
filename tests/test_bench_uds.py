from dataclasses import dataclass, field

import pytest

from atep.bench.isotp import IsoTpConfig, IsoTpEndpoint, IsoTpErrorCode
from atep.bench.link import SimulatedLink
from atep.bench.uds import (
    Nrc,
    UdsClient,
    UdsOutcome,
    UdsResult,
    physical_addressing,
    suppresses_positive_response,
)
from atep.bench.vector_trace import TraceFrame
from atep.bench.virtual_ecu import (
    Dtc,
    EcuDiagnosticProfile,
    Session,
    VirtualEcu,
    expected_key,
)

ECU_TRANSPORT = IsoTpConfig(tx_id=0x7E8, rx_id=0x7E0)


class Bench:
    def __init__(self, profile: EcuDiagnosticProfile | None = None) -> None:
        self.tester = UdsClient(physical_addressing())
        self.ecu = VirtualEcu(ECU_TRANSPORT, profile)
        self.link = SimulatedLink([self.tester, self.ecu])

    def ask(self, hex_or_bytes: str | bytes) -> UdsResult:
        request = bytes.fromhex(hex_or_bytes) if isinstance(hex_or_bytes, str) else hex_or_bytes
        self.link.submit(self.tester, self.tester.request(request, self.link.now_us))
        assert self.link.run_until(lambda: self.tester.idle)
        return self.tester.last

    def wait(self, duration_us: int) -> None:
        self.link.advance_to(self.link.now_us + duration_us)

    def unlock(self) -> None:
        assert self.ask("1003").outcome is UdsOutcome.POSITIVE
        seed = self.ask("2701").response[2:]
        assert self.ask(b"\x27\x02" + expected_key(seed)).outcome is UdsOutcome.POSITIVE


def _nrc(result: UdsResult) -> int | None:
    assert result.outcome is UdsOutcome.NEGATIVE
    return result.nrc


def test_session_control_reports_server_timing() -> None:
    bench = Bench()
    result = bench.ask("1003")
    assert result.response == bytes.fromhex("5003003201F4")
    assert bench.ecu.session is Session.EXTENDED
    assert _nrc(bench.ask("1005")) == Nrc.SUBFUNCTION_NOT_SUPPORTED
    assert _nrc(bench.ask("100301")) == Nrc.INCORRECT_MESSAGE_LENGTH


def test_s3_timeout_returns_to_default_unless_tester_present_keeps_it_alive() -> None:
    bench = Bench()
    bench.unlock()
    for _ in range(3):
        bench.wait(3_000_000)
        assert bench.ask("3E00").response == b"\x7e\x00"
    assert (bench.ecu.session, bench.ecu.unlocked) == (Session.EXTENDED, True)
    bench.wait(5_100_000)
    assert (bench.ecu.session, bench.ecu.unlocked) == (Session.DEFAULT, False)


def test_read_multiple_dids_and_reject_unknown_ones() -> None:
    bench = Bench()
    result = bench.ask("22F18CF195")
    assert result.response == b"\x62\xf1\x8cSN-0001\xf1\x95XI-2.0"
    assert _nrc(bench.ask("22F1FF")) == Nrc.REQUEST_OUT_OF_RANGE
    assert _nrc(bench.ask("22F1")) == Nrc.INCORRECT_MESSAGE_LENGTH


def test_write_needs_extended_session_and_security() -> None:
    bench = Bench()
    write = b"\x2e\xf1\x98" + b"SHOP-42"
    assert _nrc(bench.ask(write)) == Nrc.SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION
    bench.ask("1003")
    assert _nrc(bench.ask(write)) == Nrc.SECURITY_ACCESS_DENIED
    seed = bench.ask("2701").response[2:]
    bench.ask(b"\x27\x02" + expected_key(seed))
    assert bench.ask(write).response == bytes.fromhex("6EF198")
    assert bench.ask("22F198").response == b"\x62\xf1\x98SHOP-42"
    assert _nrc(bench.ask(b"\x2e\xf1\x90" + bytes(17))) == Nrc.REQUEST_OUT_OF_RANGE


def test_security_access_locks_out_after_three_wrong_keys() -> None:
    bench = Bench(EcuDiagnosticProfile(lockout_us=1_000_000))
    bench.ask("1003")
    assert _nrc(bench.ask("2702AAAA")) == Nrc.REQUEST_SEQUENCE_ERROR
    for expected in (Nrc.INVALID_KEY, Nrc.INVALID_KEY, Nrc.EXCEEDED_NUMBER_OF_ATTEMPTS):
        seed = bench.ask("2701").response[2:]
        wrong = bytes([expected_key(seed)[0] ^ 0xFF]) + expected_key(seed)[1:]
        assert _nrc(bench.ask(b"\x27\x02" + wrong)) == expected
    assert _nrc(bench.ask("2701")) == Nrc.REQUIRED_TIME_DELAY_NOT_EXPIRED
    bench.wait(1_000_000)
    assert bench.ask("2701").outcome is UdsOutcome.POSITIVE


def test_seeds_change_and_an_unlocked_ecu_returns_a_zero_seed() -> None:
    bench = Bench()
    bench.ask("1003")
    first = bench.ask("2701").response[2:]
    second = bench.ask("2701").response[2:]
    assert first != second
    bench.ask(b"\x27\x02" + expected_key(second))
    assert bench.ask("2701").response == bytes.fromhex("67010000")
    assert _nrc(bench.ask("2703")) == Nrc.SUBFUNCTION_NOT_SUPPORTED


def test_dtc_read_filters_by_status_mask_and_clear_all() -> None:
    profile = EcuDiagnosticProfile(dtcs=[Dtc(0x9A0113, 0x2F), Dtc(0xC07300, 0x08)])
    bench = Bench(profile)
    assert bench.ask("190201").response == bytes.fromhex("5902FF9A01132F")
    assert bench.ask("190208").response == bytes.fromhex("5902FF9A01132FC0730008")
    assert _nrc(bench.ask("190A")) == Nrc.SUBFUNCTION_NOT_SUPPORTED
    assert _nrc(bench.ask("14FFFF00")) == Nrc.REQUEST_OUT_OF_RANGE
    assert bench.ask("14FFFFFF").response == b"\x54"
    assert bench.ask("1902FF").response == bytes.fromhex("5902FF")


def test_reset_returns_to_default_session() -> None:
    bench = Bench()
    bench.unlock()
    assert bench.ask("1101").response == bytes.fromhex("5101")
    assert (bench.ecu.session, bench.ecu.unlocked, bench.ecu.resets) == (Session.DEFAULT, False, 1)
    assert _nrc(bench.ask("1103")) == Nrc.SUBFUNCTION_NOT_SUPPORTED


def test_unsupported_service_and_suppressed_positive_response() -> None:
    bench = Bench()
    assert _nrc(bench.ask("3101FF00")) == Nrc.SERVICE_NOT_SUPPORTED
    result = bench.ask("3E80")
    assert result.outcome is UdsOutcome.NO_RESPONSE_EXPECTED
    assert result.response_time_us == 50_000
    # A suppressed request that fails still gets its negative response.
    assert _nrc(bench.ask("1085")) == Nrc.SUBFUNCTION_NOT_SUPPORTED


def test_response_pending_extends_the_wait_to_p2_star() -> None:
    bench = Bench(EcuDiagnosticProfile(slow_dids={0xF195: 7_000_000}))
    result = bench.ask("22F195")
    assert result.outcome is UdsOutcome.POSITIVE
    assert result.pending_count == 3
    assert 7_000_000 <= result.response_time_us < 7_010_000


@dataclass
class SilentNode:
    """Receives the request but never answers, or answers once with response pending."""

    transport: IsoTpEndpoint = field(default_factory=lambda: IsoTpEndpoint(ECU_TRANSPORT))
    pending_once: bool = False

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        frames = self.transport.on_frame(frame, now_us)
        if self.transport.events and self.pending_once:
            self.transport.events.clear()
            self.pending_once = False
            frames += self.transport.send(bytes([0x7F, 0x22, 0x78]), now_us)
        return frames

    def poll(self, now_us: int) -> list[TraceFrame]:
        return self.transport.poll(now_us)

    def next_deadline_us(self) -> int | None:
        return self.transport.next_deadline_us()


@pytest.mark.parametrize(
    ("pending_once", "outcome", "elapsed"),
    [(False, UdsOutcome.P2_TIMEOUT, 50_000), (True, UdsOutcome.P2_STAR_TIMEOUT, 5_000_000)],
)
def test_client_times_out_with_p2_and_p2_star(
    pending_once: bool, outcome: UdsOutcome, elapsed: int
) -> None:
    tester = UdsClient(physical_addressing())
    link = SimulatedLink([tester, SilentNode(pending_once=pending_once)])
    link.submit(tester, tester.request(bytes.fromhex("22F190"), 0))
    link.run_until(lambda: tester.idle)
    assert tester.last.outcome is outcome
    assert elapsed <= tester.last.response_time_us < elapsed + 2_000


def test_client_reports_transport_errors_and_unexpected_responses() -> None:
    tester = UdsClient(IsoTpConfig(tx_id=0x7E0, rx_id=0x7E8, n_bs_timeout_us=1_000))
    link = SimulatedLink([tester, SilentNode(transport=IsoTpEndpoint(IsoTpConfig(0x7E8, 0x7FF)))])
    link.submit(tester, tester.request(bytes(20), 0))
    link.run_until(lambda: tester.idle)
    assert tester.last.outcome is UdsOutcome.TRANSPORT_ERROR
    assert tester.last.transport_error is IsoTpErrorCode.N_BS_TIMEOUT

    tester = UdsClient(physical_addressing())
    tester.request(bytes.fromhex("22F190"), 0)
    tester.on_frame(TraceFrame(10, 0x7E8, False, bytes.fromhex("03 6E F1 90 CC CC CC CC")), 10)
    assert tester.last.outcome is UdsOutcome.UNEXPECTED_RESPONSE
    with pytest.raises(RuntimeError):
        tester.request(b"\x10\x01", 20)
        tester.request(b"\x10\x01", 20)


def test_only_subfunction_services_can_suppress_the_positive_response() -> None:
    assert suppresses_positive_response(bytes.fromhex("3E80"))
    assert suppresses_positive_response(bytes.fromhex("1083"))
    # 0x22 has no sub-function: 0xF1 is the high byte of the DID, not a suppress bit.
    assert not suppresses_positive_response(bytes.fromhex("22F190"))
    assert not suppresses_positive_response(bytes.fromhex("3E"))


def test_expected_key_is_xor_mask() -> None:
    assert expected_key(bytes.fromhex("1234")) == bytes.fromhex("486E")
