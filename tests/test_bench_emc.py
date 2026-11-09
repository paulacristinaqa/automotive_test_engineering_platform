import pytest

from atep.bench.airbag import AcuState, half_sine_pulse
from atep.bench.airbag_bench import AcuBench, HilBench
from atep.bench.campaign import Check
from atep.bench.emc import (
    PULSES,
    Coupling,
    FscObservation,
    FunctionalStatus,
    TransientPulse,
    _max_gap,
    _readiness_lost,
)
from atep.bench.link import SimulatedLink
from atep.bench.vector_trace import TraceFrame


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, FunctionalStatus.A),
        ({"max_status_gap_us": 200_000}, FunctionalStatus.B),
        ({"frames_lost": 1}, FunctionalStatus.B),
        ({"new_dtcs": [0xC12100]}, FunctionalStatus.B),
        ({"resets": 1}, FunctionalStatus.C),
        ({"readiness_lost": True}, FunctionalStatus.C),
        ({"recovered_automatically": False}, FunctionalStatus.D),
        (
            {"recovered_automatically": False, "recovered_after_ignition_cycle": False},
            FunctionalStatus.E,
        ),
        ({"unintended_deployment": True}, FunctionalStatus.E),
    ],
)
def test_classification(changes: dict[str, object], expected: FunctionalStatus) -> None:
    observation = FscObservation(**changes)  # type: ignore[arg-type]
    assert observation.classify() is expected


def test_classes_are_ordered_best_first() -> None:
    assert FunctionalStatus.A < FunctionalStatus.B < FunctionalStatus.E
    assert Check("class", FunctionalStatus.B, FunctionalStatus.A, at_most=True).passed
    assert not Check("class", FunctionalStatus.B, FunctionalStatus.C, at_most=True).passed
    assert Check("x", 1, 1, at_most=True).expected_text == "<= 1"
    assert not Check("x", 1, "text", at_most=True).passed


def test_readiness_and_gap_helpers() -> None:
    history = [(0, False), (100, True), (500, False), (700, True)]
    assert _readiness_lost(history, 200, 400) is False
    assert _readiness_lost(history, 200, 600) is True
    assert _readiness_lost(history, 50, 80) is True  # not ready at the start
    assert _max_gap([100, 200, 450], 0, 500) == 250
    assert _max_gap([], 0, 500) == 500


def test_pulse_catalogue_and_validation() -> None:
    assert set(PULSES) == {"1", "2a", "3a", "3b", "5b"}
    pulse = PULSES["1"]
    assert pulse.coupling is Coupling.SUPPLY and pulse.peak_v < 0
    assert pulse.starts(1_000)[:2] == [1_000, 501_000]
    assert pulse.duration_us == 9 * 500_000 + 2_000
    assert PULSES["3a"].coupling is Coupling.CAN
    with pytest.raises(ValueError):
        TransientPulse("x", "", "", 1.0, 0, 1, 1, Coupling.SUPPLY)
    with pytest.raises(ValueError):
        TransientPulse("x", "", "", 1.0, 100, 50, 2, Coupling.SUPPLY)


def test_short_pulses_are_absorbed_and_overlaps_ignored() -> None:
    bench = AcuBench()
    bench.power_on()
    bench.acu.apply_transient(bench.now_us, 200.0, 500)
    assert bench.acu.transients_absorbed == 1 and bench.acu.kl30_v == 12.5
    bench.acu.apply_transient(bench.now_us, -50.0, 2_000)
    bench.acu.apply_transient(bench.now_us, 50.0, 2_000)
    assert bench.acu.transients_absorbed == 2
    with pytest.raises(ValueError):
        bench.acu.apply_transient(bench.now_us, 1.0, 0)


def test_negative_pulse_is_an_interruption_bridged_by_the_reserve() -> None:
    bench = AcuBench()
    bench.power_on()
    bench.acu.apply_transient(bench.now_us, -100.0, 2_000)
    assert bench.acu.kl30_v == 0.0 and bench.acu.reserve_until is not None
    bench.wait(10_000)
    assert bench.acu.kl30_v == 12.5 and bench.acu.reserve_until is None
    assert (bench.acu.power_cycles, bench.acu.state) == (1, AcuState.NORMAL)


def test_clamped_overvoltage_latches_the_firing_path_until_ignition_cycle() -> None:
    bench = AcuBench()
    bench.power_on()
    bench.acu.apply_transient(bench.now_us, 87.0, 400_000)
    assert bench.acu.kl30_v == 33.0 and bench.acu.firing_inhibited and not bench.acu.ready
    bench.acu.inject_crash(half_sine_pulse(bench.now_us + 10_000, peak_g=30.0, duration_ms=60))
    bench.wait(1_000_000)
    assert bench.acu.crash is None, "an inhibited firing path must not deploy"
    assert bench.acu.firing_inhibited and bench.acu.kl30_v == 12.5
    bench.acu.set_power(bench.now_us, kl15=False)
    bench.acu.set_power(bench.now_us, kl15=True)
    bench.wait(300_000)
    assert not bench.acu.firing_inhibited and bench.acu.ready


def test_moderate_overvoltage_does_not_inhibit() -> None:
    bench = AcuBench()
    bench.power_on()
    bench.acu.apply_transient(bench.now_us, 24.0, 100_000)
    assert not bench.acu.firing_inhibited


def test_disturbances_delay_frames_with_error_frames_and_bus_off() -> None:
    link = SimulatedLink([], bitrate_kbps=500)
    link.add_disturbance(0, 10_000)
    link._queue(0, [TraceFrame(0, 0x100, False, bytes(8))])
    errors = link.error_frames()
    sent = [frame for frame in link.trace if not frame.is_error_frame]
    assert len(errors) >= 32 and link.bus_off_events >= 1
    assert sent[0].timestamp_us >= 10_000
    assert link.bus_off_recovery_us == 2_816
    with pytest.raises(ValueError):
        link.add_disturbance(5, 5)


def test_frames_are_lost_after_the_maximum_delay() -> None:
    link = SimulatedLink([], max_delay_us=5_000)
    link.add_disturbance(0, 1_000_000)
    link._queue(0, [TraceFrame(0, 0x100, False, bytes(8))])
    assert len(link.lost) == 1
    assert not [frame for frame in link.trace if not frame.is_error_frame]


def test_error_frames_carry_no_data() -> None:
    with pytest.raises(ValueError):
        TraceFrame(0, 0, False, b"\x01", is_error_frame=True)


def test_transient_generator_scpi() -> None:
    bench = HilBench()
    assert bench.scpi("TRG", "PULS:CAT?") == "1,2a,3a,3b,5b"
    bench.scpi("TRG", "PULS:SEL 9")
    assert bench.scpi("TRG", "SYST:ERR?") == '-222,"Unknown pulse"'
    bench.scpi("TRG", "PULSe:SELect 2A")
    assert bench.scpi("TRG", "PULS:SEL?") == "2a"
    bench.scpi("TRG", "PULS:LEV 75")
    assert bench.scpi("TRG", "PULS:LEV?") == "7.500000E+01"
    bench.scpi("TRG", "PULS:WIDT 0.6")
    assert bench.scpi("TRG", "SYST:ERR?") == '-222,"Width exceeds the period"'
    bench.scpi("TRG", "PULS:COUN 1")
    bench.scpi("TRG", "PULS:WIDT 0.6")
    assert (bench.scpi("TRG", "PULS:COUN?"), bench.scpi("TRG", "PULS:WIDT?")) == (
        "1",
        "6.000000E-01",
    )
    bench.switch_on()
    bench.scpi("TRG", "PULS:SEL 1")
    bench.scpi("TRG", "PULS:RUN")
    assert bench.scpi("TRG", "PULS:STAT?") == "RUNNING"
    bench.scpi("TRG", "PULS:RUN")
    assert bench.scpi("TRG", "SYST:ERR?") == '-200,"Generator busy"'
    bench.wait(5_000_000)
    assert bench.scpi("TRG", "PULS:STAT?") == "IDLE"
    bench.scpi("TRG", "*RST")
    assert bench.scpi("TRG", "PULS:SEL?") == "1"
