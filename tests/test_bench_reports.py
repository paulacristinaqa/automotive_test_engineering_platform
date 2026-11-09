import csv
import io
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from atep.bench.reports import (
    CoverageStatus,
    canoe_xml,
    coverage,
    coverage_markdown,
    html_report,
    junit_xml,
    parse_requirements,
    traceability_csv,
    unknown_requirements,
    write_all,
)
from atep.bench.testunit import StepResult, TestCaseResult, TestModuleResult, Verdict


def _case(case_id: str, verdict: Verdict, requirements: list[str]) -> TestCaseResult:
    return TestCaseResult(
        case_id,
        f"title <{case_id}>",
        requirements,
        [StepResult("1", "step & check", verdict, 1_500_000, expected="1", actual="2")],
        start_us=1_000_000,
        end_us=3_000_000,
        parameters={"ohm": 1.4},
    )


MODULE = TestModuleResult(
    "Module",
    [
        _case("A", Verdict.PASS, ["BENCH-F-001"]),
        _case("B", Verdict.FAIL, ["BENCH-F-002", "BENCH-F-001"]),
        _case("C", Verdict.ERROR, []),
        _case("D", Verdict.INCONCLUSIVE, ["BENCH-F-999"]),
    ],
)

REQUIREMENTS_MD = """# Requirements

| ID | Requirement | Evidence |
|---|---|---|
| BENCH-F-001 | First. | `tests/test_a.py` |
| BENCH-F-002 | Second. | CASE-1 |
| BENCH-F-003 | Third, unit tested. | `tests/test_c.py` |
| BENCH-NF-001 | Not tested anywhere. | review |
Some text | not a row |
"""


def test_canoe_xml_has_modules_cases_steps_and_requirements() -> None:
    root = ElementTree.fromstring(canoe_xml([MODULE]))
    module = root.find("testmodule")
    assert module is not None and module.get("verdict") == "error"
    cases = module.findall("testcase")
    assert [case.get("verdict") for case in cases] == ["pass", "fail", "error", "inconclusive"]
    first = cases[0]
    assert (first.get("starttime"), first.get("endtime")) == ("1.000000", "3.000000")
    assert [item.get("id") for item in first.iter("requirement")] == ["BENCH-F-001"]
    step = first.find("teststep")
    assert step is not None and step.text == "step & check" and step.get("actual") == "2"
    assert first.find("parameter") is not None


def test_junit_counts_failures_errors_and_skips() -> None:
    suite = ElementTree.fromstring(junit_xml([MODULE])).find("testsuite")
    assert suite is not None
    assert (
        suite.get("tests"),
        suite.get("failures"),
        suite.get("errors"),
        suite.get("skipped"),
    ) == (
        "4",
        "1",
        "1",
        "1",
    )
    cases = suite.findall("testcase")
    assert cases[1].find("failure") is not None
    assert cases[2].find("error") is not None
    assert cases[3].find("skipped") is not None
    assert "expected 1, got 2" in (cases[1].find("failure").get("message") or "")  # type: ignore[union-attr]


def test_html_escapes_and_lists_failures() -> None:
    page = html_report([MODULE], title="Report <1>")
    assert "<title>Report &lt;1&gt;</title>" in page
    assert "title &lt;B&gt;" in page and "step &amp; check" in page
    assert page.count("<h3>") == 3  # every case that did not pass gets its step table


def test_traceability_rows_are_sorted_per_requirement() -> None:
    rows = list(csv.reader(io.StringIO(traceability_csv([MODULE]))))
    assert rows[0][0] == "Requirement ID"
    assert [(row[0], row[1], row[3]) for row in rows[1:]] == [
        ("BENCH-F-001", "A", "pass"),
        ("BENCH-F-001", "B", "fail"),
        ("BENCH-F-002", "B", "fail"),
        ("BENCH-F-999", "D", "inconclusive"),
    ]


def test_coverage_statuses_and_unknown_requirements() -> None:
    requirements = parse_requirements(REQUIREMENTS_MD)
    assert [item.requirement_id for item in requirements] == [
        "BENCH-F-001",
        "BENCH-F-002",
        "BENCH-F-003",
        "BENCH-NF-001",
    ]
    statuses = {
        item.requirement.requirement_id: item.status for item in coverage(requirements, [MODULE])
    }
    assert statuses == {
        "BENCH-F-001": CoverageStatus.FAILED,  # one passing and one failing case
        "BENCH-F-002": CoverageStatus.FAILED,
        "BENCH-F-003": CoverageStatus.UNIT_TESTS_ONLY,
        "BENCH-NF-001": CoverageStatus.NOT_COVERED,
    }
    assert unknown_requirements(requirements, [MODULE]) == ["BENCH-F-999"]
    passing = TestModuleResult("ok", [_case("A", Verdict.PASS, ["BENCH-F-001"])])
    assert coverage(requirements, [passing])[0].status is CoverageStatus.VERIFIED
    text = coverage_markdown(coverage(requirements, [MODULE]), unknown=["BENCH-F-999"])
    assert "0 of 4 requirements are verified" in text and "BENCH-F-999" in text


def test_write_all_is_deterministic(tmp_path: Path) -> None:
    requirements = parse_requirements(REQUIREMENTS_MD)
    first = write_all(tmp_path / "a", [MODULE], requirements=requirements)
    second = write_all(tmp_path / "b", [MODULE], requirements=requirements)
    assert first == second
    assert sorted(path.name for path in (tmp_path / "a").iterdir()) == [
        "coverage.md",
        "junit.xml",
        "report.html",
        "test-report.xml",
        "traceability.csv",
    ]
    assert "coverage.md" not in write_all(tmp_path / "c", [MODULE])
