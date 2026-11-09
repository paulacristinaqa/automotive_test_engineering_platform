import math

import pytest

from atep.bench.airbag import (
    AcuCalibration,
    AcuState,
    FailureType,
    Loop,
    LoopShort,
    dtc_code,
    half_sine_pulse,
)
from atep.bench.airbag_bench import AcuBench, HilBench
from atep.bench.instruments import (
    VoltageProfile,
    dropout,
    momentary_drop,
    overvoltage,
    slow_decrease_increase,
    standard_profiles,
    starting_profile,
)
from atep.bench.scpi import OVERLOAD


def test_profile_interpolates_ramps_and_takes_the_later_value_at_steps() -> None:
    profile = VoltageProfile("ramp", "", ((0, 12.0), (0, 6.0), (100_000, 6.0), (200_000, 12.0)))
    assert profile.voltage_at(0) == 6.0
    assert profile.voltage_at(150_000) == pytest.approx(9.0)
    assert profile.voltage_at(500_000) == 12.0
    assert profile.duration_us == 200_000
    offsets = profile.sample_offsets()
    assert offsets[:2] == [0, 100_000] and 150_000 in offsets and offsets[-1] == 200_000


@pytest.mark.parametrize(
    "points",
    [((1, 12.0),), ((0, 12.0), (10, 5.0), (5, 5.0)), ((0, 70.0),), ()],
)
def test_invalid_profiles(points: tuple[tuple[int, float], ...]) -> None:
    with pytest.raises(ValueError):
        VoltageProfile("bad", "", points)


def test_standard_profile_shapes() -> None:
    assert set(standard_profiles()) == {
        "momentary_drop",
        "dropout",
        "starting_profile",
        "slow_decrease_increase",
        "overvoltage",
    }
    assert momentary_drop().voltage_at(50_000) == 4.5
    assert dropout().voltage_at(299_999) == 0.0
    start = starting_profile()
    assert start.voltage_at(10_000) == 4.5 and start.voltage_at(500_000) == 6.5
    assert start.voltage_at(start.duration_us) == 12.0
    slow = slow_decrease_increase(rate_v_per_s=2.0)
    assert slow.voltage_at(3_000_000) == pytest.approx(6.0)
    assert overvoltage(level_v=24.0).voltage_at(1_000_000) == 24.0


def test_supply_runs_profiles_only_with_the_output_on() -> None:
    bench = HilBench()
    assert bench.scpi("PSU", "PROG:RUN overvoltage") is None
    assert bench.scpi("PSU", "SYST:ERR?") == '-200,"Output is off"'
    bench.switch_on()
    assert bench.scpi("PSU", "PROG:CAT?") == (
        "dropout,momentary_drop,overvoltage,slow_decrease_increase,starting_profile"
    )
    bench.scpi("PSU", "PROG:RUN unknown")
    assert bench.scpi("PSU", "SYST:ERR?") == '-222,"Unknown profile"'
    bench.scpi("PSU", "PROG:RUN overvoltage")
    assert bench.scpi("PSU", "PROG:STAT?") == "RUNNING"
    bench.wait(1_000_000)
    assert bench.scpi("PSU", "MEAS:VOLT?") == "1.800000E+01"
    bench.scpi("PSU", "VOLT 13")  # a new setpoint aborts the profile
    assert bench.scpi("PSU", "PROG:STAT?") == "IDLE"
    assert bench.scpi("PSU", "VOLT?") == "1.300000E+01"
    bench.scpi("PSU", "OUTP OFF")
    bench.wait(300_000)
    assert bench.scpi("PSU", "MEAS:CURR?") == "0.000000E+00"
    assert bench.acu.state is AcuState.OFF


def test_relay_card_switches_ignition_and_reports_state() -> None:
    bench = HilBench()
    bench.scpi("PSU", "OUTP ON")
    bench.scpi("REL", "ROUT:CLOS (@1,2)")
    assert bench.scpi("REL", "ROUT:CLOS? (@1:3)") == "1,1,0"
    assert bench.acu.kl15 is True
    bench.scpi("REL", "ROUT:OPEN (@1)")
    assert bench.acu.kl15 is False
    bench.scpi("REL", "ROUT:OPEN? (@1)")
    assert bench.scpi("REL", "SYST:ERR?") == '-113,"Undefined header"'


def test_fault_box_modes_reach_the_acu() -> None:
    bench = HilBench()
    bench.scpi("FIB", "ROUT:OPEN (@1)")
    bench.scpi("FIB", "ROUT:SHOR:GND (@2)")
    bench.scpi("FIB", "ROUT:SHOR:BATT (@3)")
    bench.scpi("FIB", "SOUR:RES 3.3,(@4)")
    assert bench.scpi("FIB", "ROUT:STAT? (@1:4)") == "OPEN,SHORT GND,SHORT BATT,RES 3.300"
    assert math.isinf(bench.acu.resistance[Loop.DRIVER_AIRBAG])
    assert bench.acu.loop_short[Loop.PASSENGER_AIRBAG] is LoopShort.GROUND
    assert bench.acu.loop_short[Loop.DRIVER_PRETENSIONER] is LoopShort.BATTERY
    assert bench.acu.resistance[Loop.PASSENGER_PRETENSIONER] == 3.3
    bench.scpi("FIB", "*RST")
    assert bench.scpi("FIB", "ROUT:STAT? (@1:4)") == "NOMINAL,NOMINAL,NOMINAL,NOMINAL"
    bench.scpi("FIB", "ROUT:FOO (@1)")
    assert bench.scpi("FIB", "SYST:ERR?") == '-113,"Undefined header"'


def test_multimeter_readings() -> None:
    bench = HilBench()
    bench.switch_on(volts=13.5)
    assert bench.scpi("DMM", "MEAS:VOLT:DC?") == "1.350000E+01"
    assert bench.rack.query_float("DMM", "MEAS:CURR:DC?") == pytest.approx(1.8 / 13.5)
    bench.scpi("FIB", "ROUT:OPEN (@2)")
    assert bench.scpi("DMM", "MEAS:RES? (@2)") == OVERLOAD
    bench.scpi("DMM", "MEAS:VOLT:DC 1")
    assert bench.scpi("DMM", "SYST:ERR?") == '-113,"Undefined header"'


def test_climate_chamber_ramps_at_its_rate() -> None:
    bench = HilBench()
    bench.scpi("CHAM", "TEMP:RATE 60")  # 1 degree per second
    bench.scpi("CHAM", "TEMP 30")
    assert bench.scpi("CHAM", "TEMP:SETP?") == "3.000000E+01"
    bench.wait(2_500_000)
    assert bench.rack.query_float("CHAM", "TEMP?") == pytest.approx(27.0)
    assert not bench.chamber.stable
    bench.wait(5_000_000)
    assert bench.chamber.stable and bench.acu.temperature_c == 30.0
    assert bench.scpi("CHAM", "TEMP:RATE?") == "6.000000E+01"


def test_rack_rejects_unknown_addresses_and_explains_missing_answers() -> None:
    bench = HilBench()
    with pytest.raises(KeyError):
        bench.scpi("SCOPE", "*IDN?")
    with pytest.raises(RuntimeError, match="Undefined header"):
        bench.rack.query_float("PSU", "FOO?")
    assert "PSU  FOO?" in bench.rack.log_text()


def test_acu_current_model() -> None:
    bench = AcuBench()
    assert bench.acu.supply_current_a() == pytest.approx(50e-6)
    bench.power_on(kl30_v=12.0)
    assert bench.acu.supply_current_a() == pytest.approx(0.15)
    bench.acu.set_occupancy(bench.now_us, passenger_occupied=True)
    start = bench.now_us
    bench.acu.inject_crash(half_sine_pulse(start + 10_000, peak_g=30.0, duration_ms=60))
    bench.wait(300_000)
    assert bench.acu.peak_supply_current_a(start) == pytest.approx(0.15 + 2 * 1.75)
    bench.acu.set_power(bench.now_us, kl30_v=0.0)
    assert bench.acu.supply_current_a() == 0.0


def test_shorted_loop_cannot_fire() -> None:
    bench = AcuBench()
    bench.power_on()
    bench.acu.set_loop_short(bench.now_us, Loop.DRIVER_AIRBAG, LoopShort.BATTERY)
    bench.acu.inject_crash(half_sine_pulse(bench.now_us + 10_000, peak_g=30.0, duration_ms=60))
    bench.wait(300_000)
    assert bench.acu.crash is not None
    assert bench.acu.crash.failed == [Loop.DRIVER_AIRBAG]


def test_temperature_scales_loop_resistance() -> None:
    bench = AcuBench()
    bench.acu.set_temperature(0, 85.0)
    assert bench.acu.effective_resistance(Loop.DRIVER_AIRBAG) == pytest.approx(2.2 * 1.234)
    bench.acu.set_temperature(0, -40.0)
    assert bench.acu.effective_resistance(Loop.DRIVER_AIRBAG) == pytest.approx(2.2 * 0.7465)


def test_supply_faults_debounce_longer_than_loop_faults() -> None:
    bench = AcuBench()
    bench.power_on()
    bench.acu.set_power(bench.now_us, kl30_v=8.0)
    bench.acu.set_loop_resistance(bench.now_us, Loop.DRIVER_AIRBAG, 1.0)
    bench.wait(1_000_000)
    dtcs = bench.read_dtcs()
    assert dtcs[dtc_code("B1001", FailureType.RESISTANCE_BELOW_THRESHOLD)] & 0x08
    assert not dtcs[dtc_code("B1010", FailureType.VOLTAGE_BELOW_THRESHOLD)] & 0x08
    bench.wait(1_100_000)
    assert bench.read_dtcs()[dtc_code("B1010", FailureType.VOLTAGE_BELOW_THRESHOLD)] & 0x08
    assert AcuCalibration().supply_debounce_us == 2_000_000
