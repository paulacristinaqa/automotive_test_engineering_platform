from pathlib import Path

from atep.bench.reports import CoverageStatus, coverage, parse_requirements, unknown_requirements
from atep.bench.testunit import Verdict
from tools.run_test_units_demo import REQUIREMENTS, main, run_all


def test_all_modules_pass_and_every_requirement_is_covered(tmp_path: Path) -> None:
    modules, files = run_all(tmp_path)
    failing = {
        case.case_id: [step.description for step in case.steps if step.verdict is not Verdict.PASS]
        for module in modules
        for case in module.cases
        if case.verdict is not Verdict.PASS
    }
    assert not failing, failing
    assert [module.title for module in modules] == [
        "ACU event-driven test unit",
        "ACU system tests (test table)",
        "ACU system-test campaign",
        "HiL bench campaign",
        "EMC-concept campaign",
    ]
    assert sum(len(module.cases) for module in modules) == 5 + 11 + 15 + 15 + 7
    assert set(files) == {
        "test-report.xml",
        "junit.xml",
        "report.html",
        "traceability.csv",
        "coverage.md",
    }
    requirements = parse_requirements(REQUIREMENTS.read_text(encoding="utf-8"))
    statuses = {item.status for item in coverage(requirements, modules)}
    assert CoverageStatus.NOT_COVERED not in statuses
    assert CoverageStatus.FAILED not in statuses


def test_test_cases_only_cite_documented_requirements(tmp_path: Path) -> None:
    """Traceability regression: a case must not cite a requirement the document lacks."""
    modules, _ = run_all(tmp_path)
    requirements = parse_requirements(REQUIREMENTS.read_text(encoding="utf-8"))
    assert unknown_requirements(requirements, modules) == []


def test_reports_are_reproducible(tmp_path: Path) -> None:
    _, first = run_all(tmp_path / "a")
    _, second = run_all(tmp_path / "b")
    assert first == second


def test_cli_exit_code(tmp_path: Path) -> None:
    assert main(["--output", str(tmp_path)]) == 0
