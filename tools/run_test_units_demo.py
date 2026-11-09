"""Test-unit demo and consolidated Volume XI test report (Volume XI-6).

Runs three kinds of test definitions on the virtual bench:

1. an event-driven test unit written in Python with CAPL-like primitives,
2. a JSON test table (tools/test_tables/acu_system_tests.json),
3. the ACU, HiL and EMC campaigns, converted to test modules,

then writes a CANoe-style XML report, JUnit XML, an HTML report, a traceability
CSV for ALM import, and a requirement coverage matrix read from
docs/requirements-volume-xi.md.

    python tools/run_test_units_demo.py --output out/test-units
"""

import argparse
import hashlib
import statistics
import sys
import tempfile
from pathlib import Path

from atep.bench.airbag import STATUS_E2E, Loop, half_sine_pulse
from atep.bench.e2e import E2EChecker, E2EStatus
from atep.bench.reports import parse_requirements, write_all
from atep.bench.testtable import load_test_table
from atep.bench.testunit import (
    TestContext,
    TestModule,
    TestModuleResult,
    Verdict,
    module_from_campaign,
)
from tools import run_airbag_bench_demo, run_emc_bench_demo, run_hil_bench_demo

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "tools" / "test_tables" / "acu_system_tests.json"
REQUIREMENTS = ROOT / "docs" / "requirements-volume-xi.md"

unit = TestModule("ACU event-driven test unit")


def _power_up(t: TestContext) -> None:
    t.scpi("PSU", "VOLT 12.0")
    t.scpi("PSU", "OUTP ON")
    t.scpi("REL", "ROUT:CLOS (@1)")
    t.expect_signal("acu_status", "SystemState", low=2, high=2, timeout_ms=6_500)


@unit.test_case("TU-ACU-001", "Status message cycle time and jitter", requirements=("BENCH-F-024",))
def status_cycle_time(t: TestContext) -> None:
    _power_up(t)
    times: list[int] = []
    t.on_message("acu_status", lambda _signals, now: times.append(now))
    t.wait(2_000)
    periods = [(b - a) / 1000 for a, b in zip(times, times[1:], strict=False)]
    t.check("Status frames in 2 s", 20, len(times))
    t.check("Mean cycle time (ms)", 100.0, round(statistics.mean(periods), 1))
    t.check("Cycle time jitter (ms)", 1.0, round(max(periods) - min(periods), 3), at_most=True)


@unit.test_case(
    "TU-ACU-002",
    "E2E counter and CRC on every status frame",
    requirements=("BENCH-F-020", "BENCH-F-024"),
)
def e2e_continuity(t: TestContext) -> None:
    _power_up(t)
    # E2E needs the raw payload, so this case reads the recorded frames instead of signals.
    checker = E2EChecker(STATUS_E2E)
    start = t.bench.now_us
    t.wait(3_000)
    statuses = [checker.check(frame.data) for frame in t.bench.status_frames(since_us=start)]
    t.check("First frame initialises the checker", E2EStatus.INITIAL, statuses[0])
    t.check("Every later frame is OK", {E2EStatus.OK}, set(statuses[1:]))


@unit.test_case(
    "TU-ACU-003",
    "Warning lamp reaction to an open squib loop",
    requirements=("BENCH-F-025", "BENCH-F-026"),
)
def lamp_reaction(t: TestContext) -> None:
    _power_up(t)
    t.scpi("FIB", "ROUT:OPEN (@2)")
    opened = t.now_ms
    lamp_on_at: list[float] = []

    def sample_lamp(now_us: int) -> None:  # an `on timer` handler sampling every 5 ms
        if t.bench.acu.lamp_on and not lamp_on_at:
            lamp_on_at.append(now_us / 1000)

    t.on_timer(5, sample_lamp)
    t.expect_signal("acu_status", "WarningLamp", low=1, high=1, timeout_ms=800)
    t.check(
        "Lamp reacts after the 500 ms debounce (ms)",
        True,
        bool(lamp_on_at) and 500 <= lamp_on_at[0] - opened <= 510,
    )
    t.check(
        "Lamp reported on CAN within one status period (ms)", 600.0, t.now_ms - opened, at_most=True
    )


@unit.test_case("TU-ACU-004", "Crash message latency", requirements=("BENCH-F-032",))
def crash_latency(t: TestContext) -> None:
    _power_up(t)
    start = t.bench.now_us + 10_000
    t.bench.acu.inject_crash(half_sine_pulse(start, peak_g=30.0, duration_ms=60))
    signals = t.wait_for_message("acu_crash", 50)
    if signals is None:
        t.step("Crash message within 50 ms", Verdict.FAIL, expected="frame", actual="timeout")
        return
    crash = t.bench.acu.crash
    assert crash is not None
    latency = (t.bench.now_us - crash.first_fire_us) / 1000
    t.check("Crash message after the first firing (ms)", 1.0, latency, at_most=True)
    t.check("First crash message reports belts", 1, int(signals["CrashSeverity"]))
    t.check("Driver pretensioner fired first", Loop.DRIVER_PRETENSIONER, next(iter(crash.fired)))


@unit.test_case(
    "TU-ACU-005",
    "Diagnostic read of every squib loop resistance",
    requirements=("BENCH-F-034", "BENCH-F-040"),
)
def loop_resistances(t: TestContext) -> None:
    _power_up(t)
    for channel, ohms in ((1, 1.8), (2, 2.2), (3, 3.3), (4, 4.7)):
        t.scpi("FIB", f"SOUR:RES {ohms},(@{channel})")
    for channel, ohms in ((1, 1.8), (2, 2.2), (3, 3.3), (4, 4.7)):
        did = 0x4000 + channel
        expected = f"62{did:04X}{round(ohms * 100):04X}"
        t.expect_diag(
            f"22{did:04X}", response_prefix=expected, description=f"Loop {channel} reads {ohms} ohm"
        )


def run_all(output: Path) -> tuple[list[TestModuleResult], dict[str, str]]:
    modules = [unit.run(), load_test_table(TABLE).run()]
    with tempfile.TemporaryDirectory() as scratch:
        base = Path(scratch)
        modules.append(module_from_campaign(run_airbag_bench_demo.run_campaign(base / "acu")))
        modules.append(module_from_campaign(run_hil_bench_demo.run_campaign(base / "hil")))
        modules.append(module_from_campaign(run_emc_bench_demo.run_campaign(base / "emc")))
    requirements = parse_requirements(REQUIREMENTS.read_text(encoding="utf-8"))
    files = write_all(
        output, modules, requirements=requirements, title="Volume XI bench test report"
    )
    return modules, {
        name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ATEP Volume XI-6 test units and reports")
    parser.add_argument("--output", type=Path, default=Path("out/test-units"))
    args = parser.parse_args(argv)
    modules, _ = run_all(args.output)
    for module in modules:
        print(
            f"[{module.verdict.label.upper()}] {module.title}: "
            f"{module.count(Verdict.PASS)}/{len(module.cases)} passed"
        )
    verdict = max(module.verdict for module in modules)
    print(f"Overall: {verdict.label}; reports in {args.output}")
    return 0 if verdict is Verdict.PASS else 1


if __name__ == "__main__":
    sys.exit(main())
