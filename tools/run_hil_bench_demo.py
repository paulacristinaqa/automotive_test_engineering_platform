"""HiL bench campaign (Volume XI-4): the ACU driven only through SCPI instruments and UDS.

Each case starts a fresh `HilBench`, powers the ACU with the programmable supply
and relay card, injects faults with the fault-injection box, measures with the
multimeter and changes temperature with the climate chamber. Every SCPI command
is logged. The campaign writes a JSON and Markdown report and the SCPI log.

    python tools/run_hil_bench_demo.py --output out/hil-bench
"""

import argparse
import sys
from pathlib import Path

from atep.bench.airbag import (
    SUPPLY_DTC,
    TEMPERATURE_DTC,
    AcuState,
    FailureType,
    dtc_code,
    half_sine_pulse,
)
from atep.bench.airbag_bench import HilBench
from atep.bench.campaign import (
    CampaignReport,
    Check,
    TestCase,
    dtc_status,
    print_results,
    run_case,
    write_artifact,
    write_reports,
)
from atep.bench.scpi import OVERLOAD

UNDERVOLTAGE = dtc_code(SUPPLY_DTC, FailureType.VOLTAGE_BELOW_THRESHOLD)
OVERVOLTAGE = dtc_code(SUPPLY_DTC, FailureType.VOLTAGE_ABOVE_THRESHOLD)
OVER_TEMPERATURE = dtc_code(TEMPERATURE_DTC, FailureType.OVER_TEMPERATURE)
ACTIVE = "0x2D"
HEALED = "0x2C"
INSTRUMENTS = ("PSU", "REL", "FIB", "DMM", "CHAM")


def _loop_dtc(channel: int, failure: FailureType) -> int:
    return dtc_code(f"B100{channel}", failure)


def _dtc(bench: HilBench, code: int) -> str | None:
    return dtc_status(bench.read_dtcs().get(code))


def h01_rack_identification(bench: HilBench) -> list[Check]:
    identities = [bench.scpi(address, "*IDN?") or "" for address in INSTRUMENTS]
    for address in INSTRUMENTS:
        bench.scpi(address, "*RST")
    return [
        Check(
            "Every instrument identifies itself",
            True,
            all(i.startswith("ATEP,") for i in identities),
        ),
        Check("Supply output after *RST", "0", bench.scpi("PSU", "OUTP?")),
        Check("KL15 relay after *RST", "0", bench.scpi("REL", "ROUT:CLOS? (@1)")),
        Check(
            "Fault box after *RST",
            "NOMINAL,NOMINAL,NOMINAL,NOMINAL",
            bench.scpi("FIB", "ROUT:STAT? (@1:4)"),
        ),
        Check(
            "Error queues empty",
            ['0,"No error"'] * 5,
            [bench.scpi(address, "SYST:ERR?") for address in INSTRUMENTS],
        ),
    ]


def h02_quiescent_current(bench: HilBench) -> list[Check]:
    bench.scpi("PSU", "VOLT 12.0")
    bench.scpi("PSU", "OUTP ON")
    bench.wait(500_000)
    current = bench.rack.query_float("DMM", "MEAS:CURR:DC?")
    return [
        Check("Quiescent current at or below 100 uA with KL15 open", True, current <= 100e-6),
        Check("ACU state", AcuState.OFF, bench.acu.state),
        Check(
            "No ACU frames on the bus", 0, len(bench.status_frames()) + len(bench.crash_frames())
        ),
    ]


def h03_constant_power(bench: HilBench) -> list[Check]:
    bench.switch_on()
    checks = []
    for volts in (9.0, 12.0, 16.0):
        bench.scpi("PSU", f"VOLT {volts}")
        bench.wait(50_000)
        current = bench.rack.query_float("PSU", "MEAS:CURR?")
        power = round(volts * current, 3)
        checks.append(Check(f"Input power at {volts:g} V (W)", 1.8, power))
    return checks


def h04_momentary_drop(bench: HilBench) -> list[Check]:
    bench.switch_on()
    cycles = bench.acu.power_cycles
    bench.run_profile("momentary_drop")
    return [
        Check("No ACU reset during a 100 ms drop to 4.5 V", cycles, bench.acu.power_cycles),
        Check("State and lamp", (AcuState.NORMAL, False), (bench.acu.state, bench.acu.lamp_on)),
        Check("Stored DTCs", {}, bench.read_dtcs()),
    ]


def h05_dropout(bench: HilBench) -> list[Check]:
    bench.switch_on()
    cycles = bench.acu.power_cycles
    bench.run_profile("dropout")
    return [
        Check("ACU reset after a 300 ms interruption", cycles + 1, bench.acu.power_cycles),
        Check(
            "Self-test repeats with lamp on",
            (AcuState.SELF_TEST, True),
            (bench.acu.state, bench.acu.lamp_on),
        ),
    ]


def h06_starting_profile(bench: HilBench) -> list[Check]:
    bench.switch_on()
    cycles = bench.acu.power_cycles
    bench.run_profile("starting_profile")
    status = bench.read_dtcs().get(UNDERVOLTAGE, 0)
    return [
        Check("No ACU reset during engine start", cycles, bench.acu.power_cycles),
        Check("Undervoltage DTC not confirmed", False, bool(status & 0x08)),
        Check("Lamp after engine start", False, bench.acu.lamp_on),
    ]


def h07_slow_decrease_increase(bench: HilBench) -> list[Check]:
    bench.switch_on()
    cycles = bench.acu.power_cycles
    bench.scpi("PSU", "PROG:RUN slow_decrease_increase")
    bench.wait(12_500_000)  # bottom of the ramp: 0 V
    at_bottom = (bench.acu.state, bench.rack.query_float("DMM", "MEAS:VOLT:DC?"))
    bench.wait(13_000_000)
    return [
        Check("ACU off and supply at 0 V at the bottom", (AcuState.OFF, 0.0), at_bottom),
        Check("ACU restarted on the way up", cycles + 1, bench.acu.power_cycles),
        Check("Profile finished", "IDLE", bench.scpi("PSU", "PROG:STAT?")),
        Check("Undervoltage DTC stored and healed", HEALED, _dtc(bench, UNDERVOLTAGE)),
    ]


def h08_overvoltage(bench: HilBench) -> list[Check]:
    bench.switch_on()
    bench.scpi("PSU", "PROG:RUN overvoltage")
    bench.wait(2_500_000)
    during = (_dtc(bench, OVERVOLTAGE), bench.acu.lamp_on)
    bench.wait(700_000)
    return [
        Check("Overvoltage DTC and lamp at 18 V after 2.5 s", (ACTIVE, True), during),
        Check(
            "Overvoltage DTC and lamp back at 12 V",
            (HEALED, False),
            (_dtc(bench, OVERVOLTAGE), bench.acu.lamp_on),
        ),
    ]


def h09_shorts(bench: HilBench) -> list[Check]:
    bench.switch_on()
    bench.scpi("FIB", "ROUT:SHOR:GND (@1)")
    bench.scpi("FIB", "ROUT:SHOR:BATT (@2)")
    bench.wait(600_000)
    state = bench.scpi("FIB", "ROUT:STAT? (@1:2)")
    shorts = (
        _dtc(bench, _loop_dtc(1, FailureType.SHORT_TO_GROUND)),
        _dtc(bench, _loop_dtc(2, FailureType.SHORT_TO_BATTERY)),
    )
    bench.scpi("FIB", "ROUT:CLOS (@1,2)")
    bench.wait(100_000)
    return [
        Check("Fault box state", "SHORT GND,SHORT BATT", state),
        Check("Short to ground and to battery DTCs", (ACTIVE, ACTIVE), shorts),
        Check("Lamp after repair", False, bench.acu.lamp_on),
        Check(
            "DTCs after repair",
            (HEALED, HEALED),
            (
                _dtc(bench, _loop_dtc(1, FailureType.SHORT_TO_GROUND)),
                _dtc(bench, _loop_dtc(2, FailureType.SHORT_TO_BATTERY)),
            ),
        ),
    ]


def h10_resistance_boundaries(bench: HilBench) -> list[Check]:
    """Boundary value analysis of the 1.5-5.0 ohm squib window, just inside and outside."""
    bench.switch_on()
    expected = {1.4: "0x1A", 1.5: None, 5.0: None, 5.1: "0x1B"}
    checks = []
    for ohms, failure in expected.items():
        bench.scpi("FIB", f"SOUR:RES {ohms},(@1)")
        bench.wait(600_000)
        codes = [code & 0xFF for code in bench.read_dtcs() if code >> 8 == 0x9001]
        checks.append(
            Check(
                f"Driver airbag loop DTC at {ohms} ohm",
                failure,
                f"0x{codes[0]:02X}" if codes else None,
            )
        )
        bench.scpi("FIB", "ROUT:CLOS (@1)")
        bench.ask("14FFFFFF")
    return checks


def h11_loop_resistance_measurement(bench: HilBench) -> list[Check]:
    bench.switch_on()
    bench.scpi("FIB", "SOUR:RES 4.2,(@3)")
    measured = bench.rack.query_float("DMM", "MEAS:RES? (@3)")
    bench.scpi("FIB", "ROUT:OPEN (@4)")
    did = bench.ask("224003").response
    return [
        Check("DMM reads the substituted resistance (ohm)", 4.2, round(measured, 3)),
        Check(
            "DMM reports an open loop as overload", OVERLOAD, bench.scpi("DMM", "MEAS:RES? (@4)")
        ),
        Check("ACU DID 0x4003 reads 4.20 ohm", bytes.fromhex("62 40 03 01 A4"), did),
    ]


def h12_temperature_drift(bench: HilBench) -> list[Check]:
    bench.switch_on()
    bench.scpi("CHAM", "TEMP:RATE 600")
    checks = []
    for celsius in (-40, 85):
        bench.scpi("CHAM", f"TEMP {celsius}")
        bench.wait(15_000_000)
        checks.append(Check(f"Nominal loops fault-free at {celsius} C", {}, bench.read_dtcs()))
    bench.scpi("FIB", "SOUR:RES 4.9,(@2)")
    bench.wait(600_000)
    hot = round(bench.rack.query_float("DMM", "MEAS:RES? (@2)"), 2)
    hot_dtc = _dtc(bench, _loop_dtc(2, FailureType.RESISTANCE_ABOVE_THRESHOLD))
    bench.scpi("CHAM", "TEMP 25")
    bench.wait(8_000_000)
    return [
        *checks,
        Check("4.9 ohm loop measured at 85 C (ohm)", 6.05, hot),
        Check("Loop above window at 85 C", ACTIVE, hot_dtc),
        Check("Chamber back at 25 C", "2.500000E+01", bench.scpi("CHAM", "TEMP?")),
        Check(
            "Loop DTC healed at 25 C",
            HEALED,
            _dtc(bench, _loop_dtc(2, FailureType.RESISTANCE_ABOVE_THRESHOLD)),
        ),
    ]


def h13_over_temperature(bench: HilBench) -> list[Check]:
    bench.switch_on()
    bench.scpi("CHAM", "TEMP:RATE 1000")
    bench.scpi("CHAM", "TEMP 95")
    bench.wait(8_000_000)
    return [
        Check("Over-temperature DTC at 95 C", ACTIVE, _dtc(bench, OVER_TEMPERATURE)),
        Check("Lamp", True, bench.acu.lamp_on),
    ]


def h14_firing_current(bench: HilBench) -> list[Check]:
    bench.switch_on()
    bench.acu.set_occupancy(bench.now_us, passenger_occupied=True)
    bench.scpi("PSU", "SENS:CURR:PEAK:CLE")
    idle_peak = bench.rack.query_float("PSU", "MEAS:CURR:PEAK?")
    bench.acu.inject_crash(half_sine_pulse(bench.now_us + 10_000, peak_g=30.0, duration_ms=60))
    bench.wait(300_000)
    peak = bench.rack.query_float("PSU", "MEAS:CURR:PEAK?")
    return [
        Check("Peak before the crash (A)", 0.15, round(idle_peak, 3)),
        Check("Peak with two squibs firing together (A)", 3.65, round(peak, 3)),
        Check(
            "Current back to operating level (A)",
            0.15,
            round(bench.rack.query_float("PSU", "MEAS:CURR?"), 3),
        ),
    ]


def h15_scpi_errors(bench: HilBench) -> list[Check]:
    responses = [
        bench.scpi("PSU", "FOO 1") or bench.scpi("PSU", "SYST:ERR?"),
        bench.scpi("FIB", "ROUT:OPEN (@7)") or bench.scpi("FIB", "SYST:ERR?"),
        bench.scpi("PSU", "VOLT 70") or bench.scpi("PSU", "SYST:ERR?"),
        bench.scpi("PSU", "OUTP MAYBE") or bench.scpi("PSU", "SYST:ERR?"),
        bench.scpi("PSU", "PROG:RUN overvoltage") or bench.scpi("PSU", "SYST:ERR?"),
    ]
    bench.scpi("PSU", "FOO")
    bench.scpi("PSU", "*CLS")
    cleared = bench.scpi("PSU", "SYST:ERR?")
    bench.scpi("PSU", ":OUTPut:STATe ON")
    long_form = bench.scpi("PSU", "OUTPUT?")
    return [
        Check("Unknown header", '-113,"Undefined header"', responses[0]),
        Check("Channel outside the fault box", '-222,"Channel out of range"', responses[1]),
        Check("Voltage above the supply range", '-222,"Data out of range"', responses[2]),
        Check("Invalid boolean", '-224,"Illegal parameter value"', responses[3]),
        Check("Profile with output off", '-200,"Output is off"', responses[4]),
        Check("*CLS empties the queue", '0,"No error"', cleared),
        Check("Long form with optional node: OUTPut:STATe ON", "1", long_form),
    ]


CASES: tuple[TestCase[HilBench], ...] = (
    TestCase("HIL-T01", "Rack identification and reset", ("BENCH-F-036",), h01_rack_identification),
    TestCase(
        "HIL-T02", "Quiescent current with ignition off", ("BENCH-F-043",), h02_quiescent_current
    ),
    TestCase(
        "HIL-T03",
        "Constant input power across supply range",
        ("BENCH-F-037", "BENCH-F-043"),
        h03_constant_power,
    ),
    TestCase(
        "HIL-T04",
        "Momentary drop to 4.5 V for 100 ms",
        ("BENCH-F-038", "BENCH-F-043"),
        h04_momentary_drop,
    ),
    TestCase(
        "HIL-T05", "Supply interruption for 300 ms", ("BENCH-F-038", "BENCH-F-043"), h05_dropout
    ),
    TestCase(
        "HIL-T06", "Engine starting profile", ("BENCH-F-038", "BENCH-F-043"), h06_starting_profile
    ),
    TestCase(
        "HIL-T07",
        "Slow decrease and increase of supply",
        ("BENCH-F-038", "BENCH-F-041"),
        h07_slow_decrease_increase,
    ),
    TestCase("HIL-T08", "Overvoltage 18 V", ("BENCH-F-038",), h08_overvoltage),
    TestCase("HIL-T09", "Squib loop shorts to ground and battery", ("BENCH-F-040",), h09_shorts),
    TestCase(
        "HIL-T10",
        "Squib resistance window boundary values",
        ("BENCH-F-040",),
        h10_resistance_boundaries,
    ),
    TestCase(
        "HIL-T11",
        "Loop resistance measurement",
        ("BENCH-F-040", "BENCH-F-041"),
        h11_loop_resistance_measurement,
    ),
    TestCase(
        "HIL-T12",
        "Harness resistance drift over temperature",
        ("BENCH-F-042",),
        h12_temperature_drift,
    ),
    TestCase("HIL-T13", "Over-temperature", ("BENCH-F-042",), h13_over_temperature),
    TestCase(
        "HIL-T14",
        "Squib firing current on the supply",
        ("BENCH-F-037", "BENCH-F-043"),
        h14_firing_current,
    ),
    TestCase("HIL-T15", "SCPI error handling", ("BENCH-F-036",), h15_scpi_errors),
)


def run_campaign(output: Path) -> CampaignReport:
    output.mkdir(parents=True, exist_ok=True)
    report = CampaignReport("HiL bench campaign", [])
    log: list[str] = []
    for case in CASES:
        bench = HilBench()
        report.cases.append(run_case(case, bench))
        log += [f"# {case.case_id} {case.title}", bench.rack.log_text()]
    write_artifact(output / "scpi-log.txt", "\n".join(log).encode("utf-8"), report)
    write_reports(output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ATEP Volume XI-4 HiL bench campaign")
    parser.add_argument("--output", type=Path, default=Path("out/hil-bench"))
    args = parser.parse_args(argv)
    report = run_campaign(args.output)
    print_results(report.cases)
    print(f"{'PASSED' if report.passed else 'FAILED'}; files in {args.output}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
