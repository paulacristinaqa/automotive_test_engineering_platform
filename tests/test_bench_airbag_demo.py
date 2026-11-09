import json
from pathlib import Path

import cantools

from atep.bench.airbag import AcuCalibration
from atep.bench.airbag_bench import AcuBench
from tools.run_airbag_bench_demo import CASES, main, run_campaign


def test_campaign_passes_every_case_and_writes_its_evidence(tmp_path: Path) -> None:
    report = run_campaign(tmp_path)
    failures = {
        case.case_id: [check.name for check in case.checks if not check.passed]
        for case in report.cases
        if not case.passed
    }
    assert report.passed, failures
    assert len(report.cases) == len(CASES) == 15
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "acu-severe-crash.asc",
        "acu-severe-crash.blf",
        "acu.dbc",
        "report.json",
        "report.md",
    ]
    summary = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert summary["passed"] is True
    assert all(case["requirements"] for case in summary["cases"])
    assert "| ACU-T08 | Severe frontal crash" in (tmp_path / "report.md").read_text(
        encoding="utf-8"
    )
    database = cantools.database.load_file(str(tmp_path / "acu.dbc"))
    assert isinstance(database, cantools.database.can.Database)
    assert {message.name for message in database.messages} >= {"acu_status", "acu_crash"}


def test_campaign_is_reproducible(tmp_path: Path) -> None:
    assert run_campaign(tmp_path / "a").files == run_campaign(tmp_path / "b").files


def test_campaign_rejects_a_miscalibrated_acu() -> None:
    """The tests must catch a wrong airbag threshold, not just pass on a good ACU."""
    severe = next(case for case in CASES if case.case_id == "ACU-T08")
    bench = AcuBench(calibration=AcuCalibration(airbag_threshold_kmh=60.0))
    checks = severe.run(bench)
    assert not all(check.passed for check in checks)
    assert any(check.name == "Fired loops" and not check.passed for check in checks)


def test_campaign_rejects_an_acu_without_safing_confirmation() -> None:
    misuse = next(case for case in CASES if case.case_id == "ACU-T06")
    bench = AcuBench(calibration=AcuCalibration(safing_threshold_g=0.0))
    assert not all(check.passed for check in misuse.run(bench))


def test_cli_exit_code(tmp_path: Path) -> None:
    assert main(["--output", str(tmp_path)]) == 0
