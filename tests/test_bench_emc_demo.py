from pathlib import Path

from atep.bench.airbag import AcuCalibration
from atep.bench.airbag_bench import HilBench
from atep.bench.campaign import TestCase, run_case
from tools.run_emc_bench_demo import CASES, main, run_campaign


def _case(case_id: str) -> TestCase[HilBench]:
    return next(case for case in CASES if case.case_id == case_id)


def _passes(case_id: str, calibration: AcuCalibration) -> bool:
    return run_case(_case(case_id), HilBench(calibration=calibration)).passed


def test_campaign_passes_and_writes_the_test_plan(tmp_path: Path) -> None:
    report = run_campaign(tmp_path)
    failures = {
        case.case_id: [check.name for check in case.checks if not check.passed]
        for case in report.cases
        if not case.passed
    }
    assert report.passed, failures
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "acu.dbc",
        "emc-pulse-3a.asc",
        "emc-pulse-3a.blf",
        "emc-test-plan.md",
        "report.json",
        "report.md",
    ]
    plan = (tmp_path / "emc-test-plan.md").read_text(encoding="utf-8")
    assert (
        "| EMC-T05 | 5b | Supply | 35 V (Us 87 V suppressed), 400 ms, 1x | D | D | yes | PASS |"
        in plan
    )
    assert "ErrorFrame" in (tmp_path / "emc-pulse-3a.asc").read_text(encoding="utf-8")


def test_campaign_is_reproducible(tmp_path: Path) -> None:
    assert run_campaign(tmp_path / "a").files == run_campaign(tmp_path / "b").files


def test_campaign_rejects_an_acu_without_firing_inhibit() -> None:
    assert not _passes("EMC-T05", AcuCalibration(firing_inhibit_v=40.0))


def test_campaign_rejects_an_acu_with_too_short_an_input_filter() -> None:
    """A 50 us pulse that passes the filter is clamped to 33 V and latches the inhibit."""
    assert not _passes("EMC-T02", AcuCalibration(input_filter_us=10))


def test_campaign_rejects_an_acu_whose_reserve_cannot_bridge_pulse_1() -> None:
    assert not _passes("EMC-T01", AcuCalibration(energy_reserve_us=1_000))


def test_cli_exit_code(tmp_path: Path) -> None:
    assert main(["--output", str(tmp_path)]) == 0
