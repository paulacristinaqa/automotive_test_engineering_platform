"""Airbag control unit system-test campaign on the virtual bench (Volume XI-3).

Each test case starts a fresh bench, drives the ACU like a HiL operator would
(power, squib loops, occupancy, crash pulses), and compares every observation
with its expected value. The campaign writes a JSON report, a Markdown summary,
the ACU DBC, and Vector traces of the severe-crash case.

    python tools/run_airbag_bench_demo.py --output out/airbag-bench
"""

import argparse
import math
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from atep.bench.airbag import (
    ACU_CRASH_ID,
    ACU_STATUS_ID,
    CRASH_RECORDED_DTC,
    DID_CRASH_RECORD,
    LOST_VEHICLE_STATUS_DTC,
    SUPPLY_DTC,
    AcuState,
    CrashPulse,
    CrashSeverity,
    FailureType,
    Loop,
    airbag_network_spec,
    decode,
    dtc_code,
    half_sine_pulse,
    hammer_blow,
)
from atep.bench.airbag_bench import AcuBench
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
from atep.bench.e2e import E2EStatus
from atep.bench.vector_dbc import encode_dbc, render_dbc
from atep.bench.vector_trace import render_asc, render_blf

MEASUREMENT_START = datetime(2026, 1, 1, tzinfo=UTC)


def severe_crash(start_us: int) -> CrashPulse:
    """About 28 km/h of delta-v in the 30 ms window: belts and airbags."""
    return half_sine_pulse(start_us, peak_g=30.0, duration_ms=60)


def low_crash(start_us: int) -> CrashPulse:
    """About 7.6 km/h of delta-v in the 30 ms window: belts only."""
    return half_sine_pulse(start_us, peak_g=8.0, duration_ms=60)


CONFIRMED_ACTIVE = "0x2D"  # testFailed, pending, confirmed, failed since last clear
CONFIRMED_HEALED = "0x2C"


def _loops(bench: AcuBench) -> list[str]:
    crash = bench.acu.crash
    return sorted(loop.value for loop in crash.fired) if crash else []


def t01_self_test(bench: AcuBench) -> list[Check]:
    bench.acu.set_power(bench.now_us, kl30_v=12.5, kl15=True)
    bench.wait(1_000_000)
    during = (bench.acu.state, bench.acu.lamp_on)
    bench.wait(5_100_000)
    statuses = bench.e2e_statuses(ACU_STATUS_ID)
    return [
        Check("State and lamp at 1 s", (AcuState.SELF_TEST, True), during),
        Check(
            "State and lamp after 6 s",
            (AcuState.NORMAL, False),
            (bench.acu.state, bench.acu.lamp_on),
        ),
        Check("Lamp switched off at", 6_000_000, bench.acu.lamp_history[-1][0]),
        Check("Stored DTCs", {}, bench.read_dtcs()),
        Check("Status frames in 6.1 s (100 ms cycle)", 61, len(bench.status_frames())),
        Check("Status E2E all valid", True, set(statuses[1:]) == {E2EStatus.OK}),
    ]


def _loop_fault(loop: Loop, ohms: float, failure: FailureType) -> Callable[[AcuBench], list[Check]]:
    def run(bench: AcuBench) -> list[Check]:
        code = dtc_code(
            {Loop.DRIVER_AIRBAG: "B1001", Loop.PASSENGER_AIRBAG: "B1002"}[loop], failure
        )
        bench.power_on()
        bench.acu.set_loop_resistance(bench.now_us, loop, ohms)
        bench.wait(400_000)
        before_debounce = (dtc_status(bench.read_dtcs().get(code)), bench.acu.lamp_on)
        bench.wait(200_000)
        confirmed = (dtc_status(bench.read_dtcs().get(code)), bench.acu.lamp_on, bench.acu.state)
        bench.acu.set_loop_resistance(bench.now_us, loop, 2.2)
        bench.wait(100_000)
        healed = (dtc_status(bench.read_dtcs().get(code)), bench.acu.lamp_on)
        clear = bench.ask("14FFFFFF").response
        return [
            Check("DTC and lamp before 500 ms debounce", ("0x25", False), before_debounce),
            Check(
                "DTC, lamp and state after debounce",
                (CONFIRMED_ACTIVE, True, AcuState.FAULT),
                confirmed,
            ),
            Check("DTC and lamp after repair", (CONFIRMED_HEALED, False), healed),
            Check("Clear DTC response", b"\x54", clear),
            Check("DTCs after clear", {}, bench.read_dtcs()),
        ]

    return run


def t04_undervoltage(bench: AcuBench) -> list[Check]:
    code = dtc_code(SUPPLY_DTC, FailureType.VOLTAGE_BELOW_THRESHOLD)
    bench.power_on()
    bench.acu.set_power(bench.now_us, kl30_v=8.5)
    bench.wait(2_100_000)
    low = (dtc_status(bench.read_dtcs().get(code)), bench.acu.lamp_on)
    bench.acu.set_power(bench.now_us, kl30_v=17.0)
    bench.wait(2_100_000)
    high = dtc_status(
        bench.read_dtcs().get(dtc_code(SUPPLY_DTC, FailureType.VOLTAGE_ABOVE_THRESHOLD))
    )
    bench.acu.set_power(bench.now_us, kl30_v=13.5)
    bench.wait(100_000)
    return [
        Check("Undervoltage DTC and lamp at 8.5 V", (CONFIRMED_ACTIVE, True), low),
        Check("Overvoltage DTC at 17 V", CONFIRMED_ACTIVE, high),
        Check("Lamp at 13.5 V", False, bench.acu.lamp_on),
        Check(
            "Supply DID reads 13.50 V",
            bytes.fromhex("62 40 10 05 46"),
            bench.ask("224010").response,
        ),
    ]


def t05_lost_communication(bench: AcuBench) -> list[Check]:
    bench.power_on()
    bench.vcu.set_active(bench.now_us, False)
    bench.wait(400_000)
    early = dtc_status(bench.read_dtcs().get(LOST_VEHICLE_STATUS_DTC))
    bench.wait(700_000)
    lost = (dtc_status(bench.read_dtcs().get(LOST_VEHICLE_STATUS_DTC)), bench.acu.lamp_on)
    bench.vcu.set_active(bench.now_us, True)
    bench.wait(200_000)
    return [
        Check("U0121 before the 500 ms timeout", None, early),
        Check("U0121 and lamp after timeout and debounce", (CONFIRMED_ACTIVE, True), lost),
        Check(
            "U0121 after the VCU returns",
            CONFIRMED_HEALED,
            dtc_status(bench.read_dtcs().get(LOST_VEHICLE_STATUS_DTC)),
        ),
    ]


def t06_hammer_blow(bench: AcuBench) -> list[Check]:
    bench.power_on()
    pulse = hammer_blow(bench.now_us + 10_000)
    bench.acu.inject_crash(pulse)
    bench.wait(200_000)
    threshold = bench.acu.cal.airbag_threshold_kmh
    return [
        # Without this precondition the case would pass even with safing disabled.
        Check(
            "Main sensor delta-v alone exceeds the airbag threshold",
            True,
            pulse.delta_v_kmh > threshold,
        ),
        Check("Fired loops", [], _loops(bench)),
        Check("Crash messages", 0, len(bench.crash_frames())),
        Check("State", AcuState.NORMAL, bench.acu.state),
    ]


def t07_low_severity(bench: AcuBench) -> list[Check]:
    bench.power_on()
    bench.acu.inject_crash(low_crash(bench.now_us + 10_000))
    bench.wait(300_000)
    crash = bench.acu.crash
    return [
        Check("Fired loops", ["driver_pretensioner"], _loops(bench)),
        Check("Severity", CrashSeverity.BELTS, crash.severity if crash else None),
    ]


def t08_severe_occupied(bench: AcuBench) -> list[Check]:
    bench.power_on()
    bench.acu.set_occupancy(bench.now_us, passenger_occupied=True)
    start = bench.now_us + 10_000
    bench.acu.inject_crash(severe_crash(start))
    bench.wait(300_000)
    fired = bench.acu.crash.fired if bench.acu.crash else {}
    belt_at = fired.get(Loop.DRIVER_PRETENSIONER)
    airbag_at = fired.get(Loop.DRIVER_AIRBAG)
    frames = bench.crash_frames()
    last = decode("acu-crash", frames[-1].data) if frames else {}
    record = bench.ask(f"22{DID_CRASH_RECORD:04X}").response
    return [
        Check("Fired loops", sorted(loop.value for loop in Loop), _loops(bench)),
        Check(
            "Pretensioners fire before airbags",
            True,
            belt_at is not None and airbag_at is not None and belt_at < airbag_at,
        ),
        Check(
            "Airbag fired within 30 ms of crash start",
            True,
            airbag_at is not None and airbag_at - start <= 30_000,
        ),
        Check("Crash messages (1 + 5 repeats)", 6, len(frames)),
        Check(
            "Crash message E2E",
            [E2EStatus.INITIAL] + [E2EStatus.OK] * 5,
            bench.e2e_statuses(ACU_CRASH_ID),
        ),
        Check(
            "Last crash message severity and loops",
            (2, 0x0F),
            (int(last.get("CrashSeverity", -1)), int(last.get("FiredLoops", -1))),
        ),
        Check("Crash record DID: stored, fired, failed", bytes([1, 0x0F, 0]), record[3:6]),
        Check("Crash speed in record (km/h)", 50, int.from_bytes(record[8:10], "big")),
        Check("State and lamp", (AcuState.CRASH, True), (bench.acu.state, bench.acu.lamp_on)),
        Check("Crash DTC", CONFIRMED_ACTIVE, dtc_status(bench.read_dtcs().get(CRASH_RECORDED_DTC))),
    ]


def t09_passenger_airbag_disabled(bench: AcuBench) -> list[Check]:
    bench.power_on()
    bench.acu.set_occupancy(bench.now_us, passenger_occupied=True, passenger_airbag_enabled=False)
    bench.acu.inject_crash(severe_crash(bench.now_us + 10_000))
    bench.wait(300_000)
    return [
        Check(
            "Fired loops",
            ["driver_airbag", "driver_pretensioner", "passenger_pretensioner"],
            _loops(bench),
        ),
    ]


def t10_supply_loss_during_crash(bench: AcuBench) -> list[Check]:
    bench.power_on()
    start = bench.now_us + 10_000
    bench.acu.inject_crash(severe_crash(start))
    bench.wait(10_000)
    bench.acu.set_power(bench.now_us, kl30_v=0.0)
    lost_at = bench.now_us
    bench.wait(300_000)
    return [
        Check(
            "Fired loops on energy reserve", ["driver_airbag", "driver_pretensioner"], _loops(bench)
        ),
        Check(
            "CAN frames after supply loss",
            0,
            len(bench.status_frames(since_us=lost_at + 1)) + len(bench.crash_frames()),
        ),
        Check("ACU off after the 150 ms reserve", AcuState.OFF, bench.acu.state),
    ]


def t11_supply_lost_before_crash(bench: AcuBench) -> list[Check]:
    bench.power_on()
    bench.acu.set_power(bench.now_us, kl30_v=0.0)
    bench.wait(200_000)
    bench.acu.inject_crash(severe_crash(bench.now_us + 10_000))
    bench.wait(300_000)
    return [
        Check("State", AcuState.OFF, bench.acu.state),
        Check("Fired loops", [], _loops(bench)),
    ]


def t12_crash_with_open_loop(bench: AcuBench) -> list[Check]:
    bench.power_on()
    bench.acu.set_loop_resistance(bench.now_us, Loop.DRIVER_AIRBAG, math.inf)
    bench.wait(600_000)
    bench.acu.inject_crash(severe_crash(bench.now_us + 10_000))
    bench.wait(300_000)
    crash = bench.acu.crash
    last = decode("acu-crash", bench.crash_frames()[-1].data)
    return [
        Check("Fired loops", ["driver_pretensioner"], _loops(bench)),
        Check(
            "Failed loops",
            ["driver_airbag"],
            [loop.value for loop in crash.failed] if crash else [],
        ),
        Check("Crash message failed-loop mask", 0x01, int(last["FailedLoops"])),
    ]


def t13_arming_delay(bench: AcuBench) -> list[Check]:
    bench.acu.set_power(bench.now_us, kl30_v=12.5, kl15=True)
    bench.acu.inject_crash(severe_crash(50_000))
    bench.wait(300_000)
    return [Check("Fired loops while arming", [], _loops(bench))]


def t14_clear_keeps_crash_record(bench: AcuBench) -> list[Check]:
    bench.power_on()
    bench.acu.inject_crash(severe_crash(bench.now_us + 10_000))
    bench.wait(300_000)
    response = bench.ask("14FFFFFF").response
    return [
        Check("Clear DTC response", b"\x54", response),
        Check("DTCs after clear", {CRASH_RECORDED_DTC: 0x2D}, bench.read_dtcs()),
        Check("Crash record still stored", 1, bench.ask(f"22{DID_CRASH_RECORD:04X}").response[3]),
    ]


def t15_no_second_deployment(bench: AcuBench) -> list[Check]:
    bench.power_on()
    bench.acu.inject_crash(severe_crash(bench.now_us + 10_000))
    bench.wait(1_000_000)
    first = _loops(bench)
    bench.acu.set_occupancy(bench.now_us, passenger_occupied=True)
    bench.acu.inject_crash(severe_crash(bench.now_us + 10_000))
    bench.wait(300_000)
    return [
        Check("Loops after first crash", ["driver_airbag", "driver_pretensioner"], first),
        Check("Loops after a second crash", first, _loops(bench)),
    ]


CASES: tuple[TestCase[AcuBench], ...] = (
    TestCase("ACU-T01", "Power-up self-test and cyclic status", ("BENCH-F-024",), t01_self_test),
    TestCase(
        "ACU-T02",
        "Passenger airbag loop open circuit",
        ("BENCH-F-025", "BENCH-F-026"),
        _loop_fault(Loop.PASSENGER_AIRBAG, math.inf, FailureType.CIRCUIT_OPEN),
    ),
    TestCase(
        "ACU-T03",
        "Driver airbag loop resistance too low",
        ("BENCH-F-025", "BENCH-F-026"),
        _loop_fault(Loop.DRIVER_AIRBAG, 1.0, FailureType.RESISTANCE_BELOW_THRESHOLD),
    ),
    TestCase(
        "ACU-T04", "Supply voltage out of range", ("BENCH-F-027", "BENCH-F-034"), t04_undervoltage
    ),
    TestCase("ACU-T05", "Lost vehicle status message", ("BENCH-F-028",), t05_lost_communication),
    TestCase("ACU-T06", "Misuse: hammer blow on the ACU", ("BENCH-F-030",), t06_hammer_blow),
    TestCase("ACU-T07", "Low-severity frontal crash", ("BENCH-F-029",), t07_low_severity),
    TestCase(
        "ACU-T08",
        "Severe frontal crash, passenger seat occupied",
        ("BENCH-F-029", "BENCH-F-032", "BENCH-F-034"),
        t08_severe_occupied,
    ),
    TestCase(
        "ACU-T09",
        "Severe crash with passenger airbag disabled",
        ("BENCH-F-029",),
        t09_passenger_airbag_disabled,
    ),
    TestCase(
        "ACU-T10",
        "Supply loss at crash start (energy reserve)",
        ("BENCH-F-031",),
        t10_supply_loss_during_crash,
    ),
    TestCase("ACU-T11", "Supply lost before crash", ("BENCH-F-031",), t11_supply_lost_before_crash),
    TestCase(
        "ACU-T12", "Crash with an open airbag loop", ("BENCH-F-033",), t12_crash_with_open_loop
    ),
    TestCase("ACU-T13", "Crash during arming delay", ("BENCH-F-029",), t13_arming_delay),
    TestCase(
        "ACU-T14",
        "DTC clear keeps the crash record",
        ("BENCH-F-026", "BENCH-F-032"),
        t14_clear_keeps_crash_record,
    ),
    TestCase(
        "ACU-T15", "No second deployment after a crash", ("BENCH-F-032",), t15_no_second_deployment
    ),
)


def run_campaign(output: Path) -> CampaignReport:
    output.mkdir(parents=True, exist_ok=True)
    report = CampaignReport("ACU system-test campaign", [])
    severe_trace = None
    for case in CASES:
        bench = AcuBench()
        report.cases.append(run_case(case, bench))
        if case.case_id == "ACU-T08":
            severe_trace = bench.link.trace
    write_artifact(output / "acu.dbc", encode_dbc(render_dbc(airbag_network_spec())), report)
    if severe_trace is not None:
        write_artifact(
            output / "acu-severe-crash.asc",
            render_asc(severe_trace, measurement_start=MEASUREMENT_START).encode("utf-8"),
            report,
        )
        write_artifact(
            output / "acu-severe-crash.blf",
            render_blf(severe_trace, measurement_start=MEASUREMENT_START),
            report,
        )
    write_reports(output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ATEP Volume XI-3 ACU system-test campaign")
    parser.add_argument("--output", type=Path, default=Path("out/airbag-bench"))
    args = parser.parse_args(argv)
    report = run_campaign(args.output)
    print_results(report.cases)
    print(f"{'PASSED' if report.passed else 'FAILED'}; files in {args.output}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
