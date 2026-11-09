"""Transient and EMC-concept campaign (Volume XI-5).

An EMC test plan states, for each pulse, the level, repetitions, coupling and the
functional status class (A best, E worst) the ACU must reach. This campaign plays
each pulse with the SCPI transient generator, observes the ACU during and after
the exposure, classifies the result, and checks the class against the plan. In
every test the ACU must never deploy.

This is a conceptual model, not an EMC measurement.

    python tools/run_emc_bench_demo.py --output out/emc-bench
"""

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from atep.bench.airbag import FIRING_INHIBIT_DTC, LOST_VEHICLE_STATUS_DTC, airbag_network_spec
from atep.bench.airbag_bench import HilBench
from atep.bench.campaign import (
    CampaignReport,
    CaseResult,
    Check,
    TestCase,
    dtc_status,
    print_results,
    run_case,
    write_artifact,
    write_reports,
)
from atep.bench.emc import FSC_MEANING, PULSES, FscObservation, FunctionalStatus, observe
from atep.bench.vector_dbc import encode_dbc, render_dbc
from atep.bench.vector_trace import render_asc, render_blf

MEASUREMENT_START = datetime(2026, 1, 1, tzinfo=UTC)
CLASS_CHECK = "Functional status class"


def _common(observation: FscObservation, required: FunctionalStatus) -> list[Check]:
    return [
        Check(CLASS_CHECK, required, observation.classify(), at_most=True),
        Check("No unintended deployment", False, observation.unintended_deployment),
    ]


def _pulse_case(
    pulse: str,
    required: FunctionalStatus,
    extra: Callable[[HilBench, FscObservation], list[Check]] | None = None,
    *,
    commands: tuple[str, ...] = (),
) -> Callable[[HilBench], list[Check]]:
    def run(bench: HilBench) -> list[Check]:
        bench.switch_on()
        bench.scpi("TRG", f"PULS:SEL {pulse}")
        for command in commands:
            bench.scpi("TRG", command)
        width = bench.rack.query_float("TRG", "PULS:WIDT?")
        count = int(bench.scpi("TRG", "PULS:COUN?") or "1")
        period = PULSES[pulse].period_us
        exposure = round((count - 1) * period + width * 1_000_000) + 100_000
        bench.scpi("TRG", "PULS:RUN")
        observation = observe(bench, exposure_us=exposure)
        checks = _common(observation, required)
        if extra is not None:
            checks += extra(bench, observation)
        checks.append(
            Check(
                "Generator accepted every command", '0,"No error"', bench.scpi("TRG", "SYST:ERR?")
            )
        )
        return checks

    return run


def _pulse_1_extra(bench: HilBench, observation: FscObservation) -> list[Check]:
    return [Check("No ACU reset: the energy reserve bridges 2 ms", 0, observation.resets)]


def _pulse_2a_extra(bench: HilBench, observation: FscObservation) -> list[Check]:
    return [Check("Pulses absorbed by the input filter", 10, bench.acu.transients_absorbed)]


def _burst_extra(bench: HilBench, observation: FscObservation) -> list[Check]:
    return [
        Check("Error frames recorded on the bus", True, observation.error_frames > 0),
        Check(
            "Longest gap between ACU status frames (us)",
            150_000,
            observation.max_status_gap_us,
            at_most=True,
        ),
        Check("Frames lost", 0, observation.frames_lost),
    ]


def _long_burst_extra(bench: HilBench, observation: FscObservation) -> list[Check]:
    return [
        Check(
            "U0121 recorded while the vehicle status was blocked",
            [f"0x{LOST_VEHICLE_STATUS_DTC:06X}"],
            [f"0x{code:06X}" for code in observation.new_dtcs],
        ),
        # The timeout lasts about 300 ms, less than the 500 ms debounce: pending, never confirmed.
        Check(
            "U0121 pending, not confirmed, healed",
            "0x24",
            dtc_status(bench.read_dtcs().get(LOST_VEHICLE_STATUS_DTC)),
        ),
        Check("CAN controller reached bus-off and recovered", True, bench.link.bus_off_events > 0),
    ]


def emc_t05_load_dump(bench: HilBench) -> list[Check]:
    bench.switch_on()
    bench.scpi("TRG", "PULS:SEL 5b")
    bench.scpi("TRG", "PULS:RUN")

    def probe() -> tuple[bool, bool, str | None]:
        return (
            bench.acu.firing_inhibited,
            bench.acu.lamp_on,
            dtc_status(bench.read_dtcs().get(FIRING_INHIBIT_DTC)),
        )

    observation = observe(bench, exposure_us=500_000, probe_after_us=450_000, probe=probe)
    # 450 ms into the dump the 500 ms DTC debounce has not run out yet.
    return [
        *_common(observation, FunctionalStatus.D),
        Check(
            "Firing path inhibited and lamp on during the dump (inhibit, lamp, DTC)",
            (True, False, "0x25"),
            observation.probe,
        ),
        Check(
            "Recovered after an ignition cycle", True, observation.recovered_after_ignition_cycle
        ),
        Check(
            "Firing inhibit DTC stored and healed after the ignition cycle",
            "0x2C",
            dtc_status(bench.read_dtcs().get(FIRING_INHIBIT_DTC)),
        ),
        Check("Firing path enabled again", True, bench.acu.ready),
    ]


def emc_t07_interruption(bench: HilBench) -> list[Check]:
    bench.switch_on()
    bench.scpi("PSU", "PROG:RUN dropout")
    observation = observe(bench, exposure_us=400_000)
    return [
        *_common(observation, FunctionalStatus.C),
        Check(
            "ACU reset once and recovered by itself",
            (1, True),
            (observation.resets, observation.recovered_automatically),
        ),
    ]


CASES: tuple[TestCase[HilBench], ...] = (
    TestCase(
        "EMC-T01",
        "ISO 7637-2 pulse 1, -100 V, 2 ms, 10x",
        ("BENCH-F-045", "BENCH-F-047", "BENCH-NF-015"),
        _pulse_case("1", FunctionalStatus.B, _pulse_1_extra),
    ),
    TestCase(
        "EMC-T02",
        "ISO 7637-2 pulse 2a, +50 V, 50 us, 10x",
        ("BENCH-F-045", "BENCH-F-046", "BENCH-NF-015"),
        _pulse_case("2a", FunctionalStatus.A, _pulse_2a_extra),
    ),
    TestCase(
        "EMC-T03",
        "ISO 7637-2 pulse 3a coupled to CAN, 10 ms bursts",
        ("BENCH-F-045", "BENCH-F-048", "BENCH-NF-015"),
        _pulse_case("3a", FunctionalStatus.A, _burst_extra),
    ),
    TestCase(
        "EMC-T04",
        "ISO 7637-2 pulse 3b coupled to CAN, 10 ms bursts",
        ("BENCH-F-045", "BENCH-F-048", "BENCH-NF-015"),
        _pulse_case("3b", FunctionalStatus.A, _burst_extra),
    ),
    TestCase(
        "EMC-T05",
        "Load dump 5b, 35 V suppressed, 400 ms",
        ("BENCH-F-046", "BENCH-F-047", "BENCH-NF-015"),
        emc_t05_load_dump,
    ),
    TestCase(
        "EMC-T06",
        "CAN disturbance burst of 800 ms",
        ("BENCH-F-048", "BENCH-F-049", "BENCH-NF-015"),
        _pulse_case(
            "3a", FunctionalStatus.B, _long_burst_extra, commands=("PULS:COUN 1", "PULS:WIDT 0.8")
        ),
    ),
    TestCase(
        "EMC-T07",
        "Supply interruption of 300 ms",
        ("BENCH-F-047", "BENCH-NF-015"),
        emc_t07_interruption,
    ),
)

PLAN = {
    "EMC-T01": ("1", "Supply", "-100 V, 2 ms, every 0.5 s, 10x"),
    "EMC-T02": ("2a", "Supply", "+50 V, 50 us, every 0.5 s, 10x"),
    "EMC-T03": ("3a", "CAN (capacitive)", "10 ms bursts every 100 ms, 10x"),
    "EMC-T04": ("3b", "CAN (capacitive)", "10 ms bursts every 100 ms, 10x"),
    "EMC-T05": ("5b", "Supply", "35 V (Us 87 V suppressed), 400 ms, 1x"),
    "EMC-T06": ("3a", "CAN (capacitive)", "one 800 ms burst"),
    "EMC-T07": ("ISO 16750-2", "Supply", "0 V for 300 ms"),
}


def test_plan_markdown(cases: list[CaseResult]) -> str:
    lines = [
        "# EMC test plan and results (conceptual)",
        "",
        "Device: virtual airbag control unit. Levels are illustrative; this is not an EMC "
        "measurement.",
        "",
        "| Test | Pulse | Coupling | Level | Required | Achieved | No deployment | Verdict |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in cases:
        pulse, coupling, level = PLAN[case.case_id]
        fsc = next(check for check in case.checks if check.name == CLASS_CHECK)
        safe = next(check for check in case.checks if check.name == "No unintended deployment")
        lines.append(
            f"| {case.case_id} | {pulse} | {coupling} | {level} | {fsc.expected_text[3:]} | "
            f"{getattr(fsc.actual, 'name', fsc.actual)} | {'yes' if safe.passed else 'NO'} | "
            f"{'PASS' if case.passed else 'FAIL'} |"
        )
    lines += ["", "| Class | Meaning |", "|---|---|"]
    lines += [f"| {item.name} | {FSC_MEANING[item]} |" for item in FunctionalStatus]
    return "\n".join(lines) + "\n"


def run_campaign(output: Path) -> CampaignReport:
    output.mkdir(parents=True, exist_ok=True)
    report = CampaignReport("EMC-concept campaign", [])
    burst_trace = None
    for case in CASES:
        bench = HilBench()
        report.cases.append(run_case(case, bench))
        if case.case_id == "EMC-T03":
            burst_trace = bench.link.trace
    write_artifact(
        output / "emc-test-plan.md", test_plan_markdown(report.cases).encode("utf-8"), report
    )
    write_artifact(output / "acu.dbc", encode_dbc(render_dbc(airbag_network_spec())), report)
    if burst_trace is not None:
        write_artifact(
            output / "emc-pulse-3a.asc",
            render_asc(burst_trace, measurement_start=MEASUREMENT_START).encode("utf-8"),
            report,
        )
        write_artifact(
            output / "emc-pulse-3a.blf",
            render_blf(burst_trace, measurement_start=MEASUREMENT_START),
            report,
        )
    write_reports(output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ATEP Volume XI-5 EMC-concept campaign")
    parser.add_argument("--output", type=Path, default=Path("out/emc-bench"))
    args = parser.parse_args(argv)
    report = run_campaign(args.output)
    print_results(report.cases)
    print(f"{'PASSED' if report.passed else 'FAILED'}; files in {args.output}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
