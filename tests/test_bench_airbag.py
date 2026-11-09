import math

import cantools
import pytest

from atep.bench.airbag import (
    ACU_STATUS_ID,
    CRASH_RECORDED_DTC,
    DID_SYSTEM_STATE,
    LOOP_DID,
    AcuCalibration,
    AcuState,
    CrashPulse,
    Loop,
    airbag_network_spec,
    dtc_code,
    half_sine_pulse,
    hammer_blow,
)
from atep.bench.airbag_bench import AcuBench, parse_dtc_response
from atep.bench.vector_dbc import render_dbc
from atep.bench.vector_trace import TraceFrame


@pytest.mark.parametrize(
    ("text", "failure", "expected"),
    [
        ("P0300", 0x00, 0x030000),
        ("C0035", 0x00, 0x403500),
        ("B1001", 0x13, 0x900113),
        ("U0121", 0x00, 0xC12100),
    ],
)
def test_dtc_code_encoding(text: str, failure: int, expected: int) -> None:
    assert dtc_code(text, failure) == expected


@pytest.mark.parametrize(
    ("text", "failure"), [("X0001", 0), ("B4001", 0), ("B10G1", 0), ("B100", 0)]
)
def test_dtc_code_rejects_invalid_text(text: str, failure: int) -> None:
    with pytest.raises(ValueError):
        dtc_code(text, failure)


def test_crash_pulses_have_the_expected_delta_v() -> None:
    severe = half_sine_pulse(0, peak_g=30.0, duration_ms=60)
    analytic = 30.0 * 9.80665 * 0.060 * 2 / math.pi * 3.6
    assert severe.delta_v_kmh == pytest.approx(analytic, rel=1e-3)
    hammer = hammer_blow(0)
    assert max(hammer.main_g) > 190 and set(hammer.safing_g) == {1.0}
    # Strong enough that only the safing sensor can prevent an airbag deployment.
    assert hammer.delta_v_kmh > AcuCalibration().airbag_threshold_kmh
    with pytest.raises(ValueError):
        CrashPulse(0, 500, (1.0,), ())
    with pytest.raises(ValueError):
        CrashPulse(0, 0, (1.0,), (1.0,))


def test_acu_is_silent_without_ignition_and_shuts_down_on_kl15_off() -> None:
    bench = AcuBench()
    bench.wait(1_000_000)
    assert (bench.acu.state, bench.status_frames()) == (AcuState.OFF, [])
    bench.power_on()
    assert bench.acu.state == AcuState.NORMAL
    bench.acu.set_power(bench.now_us, kl15=False)
    off_at = bench.now_us
    bench.wait(500_000)
    assert (bench.acu.state, bench.status_frames(since_us=off_at + 1)) == (AcuState.OFF, [])


def test_power_cycle_repeats_the_self_test_and_keeps_dtcs() -> None:
    bench = AcuBench()
    bench.power_on()
    bench.acu.set_loop_resistance(bench.now_us, Loop.DRIVER_PRETENSIONER, 8.0)
    bench.wait(600_000)
    code = dtc_code("B1003", 0x1B)
    assert bench.read_dtcs()[code] == 0x2D
    bench.acu.set_power(bench.now_us, kl15=False)
    bench.wait(1_000_000)
    bench.acu.set_power(bench.now_us, kl15=True)
    bench.wait(1_000_000)
    assert bench.acu.power_cycles == 2
    assert bench.acu.state is AcuState.SELF_TEST
    assert bench.read_dtcs()[code] & 0x08


def test_supply_returning_within_the_reserve_keeps_the_acu_running() -> None:
    bench = AcuBench()
    bench.power_on()
    bench.acu.set_power(bench.now_us, kl30_v=0.0)
    bench.wait(100_000)
    bench.acu.set_power(bench.now_us, kl30_v=12.0)
    bench.wait(300_000)
    assert bench.acu.state is AcuState.NORMAL
    assert bench.acu.power_cycles == 1
    assert bench.status_frames(since_us=bench.now_us - 200_000)


def test_low_crash_fires_both_pretensioners_when_the_passenger_seat_is_occupied() -> None:
    bench = AcuBench()
    bench.power_on()
    bench.acu.set_occupancy(bench.now_us, passenger_occupied=True, driver_buckled=False)
    bench.acu.inject_crash(half_sine_pulse(bench.now_us + 10_000, peak_g=8.0, duration_ms=60))
    bench.wait(300_000)
    assert bench.acu.crash is not None
    assert list(bench.acu.crash.fired) == [Loop.PASSENGER_PRETENSIONER]
    with pytest.raises(ValueError):
        bench.acu.inject_crash(half_sine_pulse(0, peak_g=1.0, duration_ms=1))


def test_diagnostic_dids_report_live_values() -> None:
    bench = AcuBench()
    bench.power_on()
    bench.acu.set_loop_resistance(bench.now_us, Loop.PASSENGER_AIRBAG, math.inf)
    response = bench.ask(
        f"22{LOOP_DID[Loop.DRIVER_AIRBAG]:04X}{LOOP_DID[Loop.PASSENGER_AIRBAG]:04X}"
    )
    assert response.response == bytes.fromhex("62 4001 00DC 4002 FFFF")
    assert bench.ask(f"22{DID_SYSTEM_STATE:04X}").response == bytes.fromhex("62 4030 02 00")
    with pytest.raises(ValueError):
        bench.acu.set_loop_resistance(bench.now_us, Loop.DRIVER_AIRBAG, -1.0)


def test_status_frames_decode_with_cantools_from_the_exported_dbc() -> None:
    database = cantools.database.load_string(
        render_dbc(airbag_network_spec()), database_format="dbc"
    )
    assert isinstance(database, cantools.database.can.Database)
    bench = AcuBench(speed_kmh=87.25)
    bench.power_on()
    bench.acu.set_occupancy(bench.now_us, passenger_occupied=True)
    bench.wait(200_000)
    decoded = database.decode_message(ACU_STATUS_ID, bench.status_frames()[-1].data)
    assert isinstance(decoded, dict)
    assert decoded["SystemState"] == AcuState.NORMAL
    assert (
        decoded["WarningLamp"],
        decoded["PassengerAirbagEnabled"],
        decoded["DriverBuckled"],
    ) == (
        0,
        1,
        1,
    )
    assert bench.acu.vehicle_speed_kmh == pytest.approx(87.25)


def test_lamp_history_answers_for_any_time() -> None:
    bench = AcuBench()
    bench.power_on()
    assert bench.acu.lamp_at(3_000_000) is True
    assert bench.acu.lamp_at(6_000_000) is False
    assert bench.acu.lamp_at(0) is True


def test_crash_dtc_survives_a_clear() -> None:
    bench = AcuBench()
    bench.power_on()
    bench.acu.inject_crash(half_sine_pulse(bench.now_us + 10_000, peak_g=30.0, duration_ms=60))
    bench.wait(300_000)
    bench.acu.clear_dtcs()
    assert set(bench.acu.dtcs) == {CRASH_RECORDED_DTC}


def test_frames_are_ignored_while_off() -> None:
    bench = AcuBench()
    assert bench.acu.on_frame(TraceFrame(0, 0x7E2, False, bytes.fromhex("0322F190")), 0) == []


def test_parse_dtc_response() -> None:
    assert parse_dtc_response(bytes.fromhex("5902FF 9001132D C1210008")) == {
        0x900113: 0x2D,
        0xC12100: 0x08,
    }
    with pytest.raises(ValueError):
        parse_dtc_response(bytes.fromhex("7F1911"))


def test_custom_calibration_changes_behaviour() -> None:
    bench = AcuBench(calibration=AcuCalibration(airbag_threshold_kmh=60.0))
    bench.power_on()
    bench.acu.inject_crash(half_sine_pulse(bench.now_us + 10_000, peak_g=30.0, duration_ms=60))
    bench.wait(300_000)
    assert bench.acu.crash is not None
    assert Loop.DRIVER_AIRBAG not in bench.acu.crash.fired
