import os

import pytest
from crccheck.crc import Crc8SaeJ1850  # type: ignore[import-untyped]

from atep.bench.cyclic import CyclicFault, CyclicSender, E2EReceiver
from atep.bench.e2e import (
    E2EChecker,
    E2EConfig,
    E2EProtector,
    E2EStatus,
    compute_crc,
    crc8_sae_j1850,
)
from atep.bench.link import SimulatedLink
from atep.bench.supervision import (
    SupervisedMessage,
    SupervisionEvent,
    SupervisionState,
    TimeoutMonitor,
)
from atep.bench.vector_trace import TraceFrame

CONFIG = E2EConfig(data_id=0x0123, length=8)


def test_crc_matches_the_sae_j1850_check_value_and_an_independent_library() -> None:
    assert crc8_sae_j1850(b"123456789") == 0x4B
    for size in range(0, 64):
        data = os.urandom(size)
        assert crc8_sae_j1850(data) == Crc8SaeJ1850.calc(data)


def test_crc_covers_the_data_id() -> None:
    payload = bytes(8)
    other = E2EConfig(data_id=0x0124, length=8)
    assert compute_crc(CONFIG, payload) != compute_crc(other, payload)


def test_protector_counts_zero_to_fourteen_and_keeps_payload() -> None:
    protector = E2EProtector(CONFIG)
    counters = [protector.protect(bytes([0, 0xA0, 1, 2, 3, 4, 5, 6]))[1] for _ in range(16)]
    assert [value & 0x0F for value in counters] == [*range(15), 0]
    assert all(value & 0xF0 == 0xA0 for value in counters)
    with pytest.raises(ValueError):
        protector.protect(bytes(7))


def test_checker_classifies_every_case() -> None:
    protector = E2EProtector(CONFIG)
    frames = [protector.protect(bytes(8)) for _ in range(8)]
    checker = E2EChecker(CONFIG)
    corrupted = bytes([frames[1][0] ^ 1]) + frames[1][1:]
    invalid_counter = bytearray(frames[2])
    invalid_counter[1] |= 0x0F
    invalid_counter[0] = compute_crc(CONFIG, bytes(invalid_counter))
    observed = [
        checker.check(frames[0]),
        checker.check(corrupted),
        checker.check(frames[1]),
        checker.check(frames[1]),
        checker.check(bytes(invalid_counter)),
        checker.check(frames[3]),
        checker.check(frames[7]),
        checker.check(bytes(3)),
    ]
    assert observed == [
        E2EStatus.INITIAL,
        E2EStatus.WRONG_CRC,
        E2EStatus.OK,
        E2EStatus.REPEATED,
        E2EStatus.INVALID_COUNTER,
        E2EStatus.OK_SOME_LOST,
        E2EStatus.WRONG_SEQUENCE,
        E2EStatus.WRONG_CRC,
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data_id": 0x10000},
        {"crc_byte": 1, "counter_byte": 1},
        {"crc_byte": 8},
        {"max_delta_counter": 15},
    ],
)
def test_invalid_e2e_configurations(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        E2EConfig(**({"data_id": 1, "length": 8} | kwargs))


def test_monitor_reports_never_received_messages_and_recovery_debounce() -> None:
    monitor = TimeoutMonitor(
        [
            SupervisedMessage("airbag_status", 0x50, 10_000, 50_000, recovery_frames=2),
            SupervisedMessage("never_sent", 0x51, 10_000, 30_000),
        ]
    )
    assert monitor.state("airbag_status") is SupervisionState.WAITING
    monitor.on_frame(TraceFrame(5_000, 0x50, False, b"\x00"), 5_000)
    monitor.poll(60_000)
    assert monitor.state("airbag_status") is SupervisionState.TIMEOUT
    monitor.on_frame(TraceFrame(70_000, 0x50, False, b"\x00"), 70_000)
    assert monitor.state("airbag_status") is SupervisionState.TIMEOUT
    monitor.on_frame(TraceFrame(80_000, 0x50, False, b"\x00"), 80_000)
    assert monitor.events == [
        SupervisionEvent("airbag_status", SupervisionState.OK, 5_000),
        SupervisionEvent("never_sent", SupervisionState.TIMEOUT, 30_000),
        SupervisionEvent("airbag_status", SupervisionState.TIMEOUT, 55_000),
        SupervisionEvent("airbag_status", SupervisionState.OK, 80_000),
    ]
    assert monitor.received("airbag_status") == 3
    monitor.on_frame(TraceFrame(80_000, 0x99, False, b""), 80_000)
    with pytest.raises(KeyError):
        monitor.state("unknown")


def test_monitor_rejects_bad_configuration() -> None:
    with pytest.raises(ValueError):
        SupervisedMessage("x", 0x1, 10_000, 5_000)
    with pytest.raises(ValueError):
        SupervisedMessage("x", 0x1, 10_000, 20_000, recovery_frames=0)
    message = SupervisedMessage("x", 0x1, 10_000, 20_000)
    with pytest.raises(ValueError):
        TimeoutMonitor([message, message])


def test_cyclic_sender_with_faults_feeds_receiver_and_monitor() -> None:
    faults = {2: CyclicFault.CORRUPT_CRC, 4: CyclicFault.DROP, 5: CyclicFault.DROP}
    faults |= {6: CyclicFault.DROP, 7: CyclicFault.DROP}
    sender = CyclicSender(0x101, 10_000, CONFIG, stop_after_us=100_000, faults=faults)
    receiver = E2EReceiver(0x101, CONFIG)
    monitor = TimeoutMonitor([SupervisedMessage("torque", 0x101, 10_000, 30_000)])
    link = SimulatedLink([sender, receiver, monitor])
    link.advance_to(200_000)
    assert receiver.statuses() == [
        E2EStatus.INITIAL,
        E2EStatus.OK,
        E2EStatus.WRONG_CRC,
        E2EStatus.OK_SOME_LOST,
        E2EStatus.WRONG_SEQUENCE,
        E2EStatus.OK,
        E2EStatus.OK,
    ]
    assert [event.state for event in monitor.events] == [
        SupervisionState.OK,
        SupervisionState.TIMEOUT,
        SupervisionState.OK,
        SupervisionState.TIMEOUT,
    ]
    # Cycles 0-10 at 10 ms, four dropped; the corrupted frame is still sent.
    assert len(link.trace) == 11 - 4
    with pytest.raises(ValueError):
        CyclicSender(0x1, 0, CONFIG)
