import json
from dataclasses import replace
from pathlib import Path

from atep.bench.airbag import AcuCalibration
from atep.bench.airbag_bench import HilBench
from atep.bench.campaign import TestCase, run_case
from tools.run_hil_bench_demo import CASES, main, run_campaign


def _case(case_id: str) -> TestCase[HilBench]:
    return next(case for case in CASES if case.case_id == case_id)


def test_campaign_passes_and_writes_reports_and_scpi_log(tmp_path: Path) -> None:
    report = run_campaign(tmp_path)
    failures = {
        c.case_id: [k.name for k in c.checks if not k.passed] for c in report.cases if not c.passed
    }
    assert report.passed, failures
    assert len(report.cases) == 15
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "report.json",
        "report.md",
        "scpi-log.txt",
    ]
    log = (tmp_path / "scpi-log.txt").read_text(encoding="utf-8")
    assert "# HIL-T08 Overvoltage 18 V" in log
    assert "PSU  PROG:RUN overvoltage" in log
    summary = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert summary["title"] == "HiL bench campaign" and summary["passed"] is True


def test_campaign_is_reproducible(tmp_path: Path) -> None:
    assert run_campaign(tmp_path / "a").files == run_campaign(tmp_path / "b").files


def _run_with(case_id: str, calibration: AcuCalibration) -> bool:
    return run_case(_case(case_id), HilBench(calibration=calibration)).passed


def test_campaign_rejects_excessive_quiescent_current() -> None:
    assert not _run_with("HIL-T02", AcuCalibration(quiescent_current_a=250e-6))


def test_campaign_rejects_a_supply_debounce_shorter_than_engine_start() -> None:
    """With the loop debounce on the supply, cranking would confirm an undervoltage DTC."""
    defective = replace(AcuCalibration(), supply_debounce_us=500_000)
    assert not _run_with("HIL-T06", defective)
    assert _run_with("HIL-T06", AcuCalibration())


def test_campaign_rejects_a_missing_energy_reserve() -> None:
    assert not _run_with("HIL-T04", AcuCalibration(energy_reserve_us=50_000))


def test_campaign_rejects_a_wrong_resistance_window() -> None:
    assert not _run_with("HIL-T10", AcuCalibration(loop_min_ohm=1.0))


def test_cli_exit_code(tmp_path: Path) -> None:
    assert main(["--output", str(tmp_path)]) == 0
