"""Shared test-campaign model: test cases, checks, results and reports.

A test case runs on a fresh bench and returns checks. Each check compares an
expected value with the observed one, so a report always shows both.
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path


@dataclass
class Check:
    name: str
    expected: object
    actual: object

    @property
    def passed(self) -> bool:
        return self.expected == self.actual


@dataclass
class CaseResult:
    case_id: str
    title: str
    requirements: list[str]
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)


@dataclass(frozen=True)
class TestCase[BenchT]:
    case_id: str
    title: str
    requirements: tuple[str, ...]
    run: Callable[[BenchT], list[Check]]

    __test__ = False  # not a pytest test class


@dataclass
class CampaignReport:
    title: str
    cases: list[CaseResult]
    files: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return bool(self.cases) and all(case.passed for case in self.cases)


def run_case[BenchT](case: TestCase[BenchT], bench: BenchT) -> CaseResult:
    result = CaseResult(case.case_id, case.title, list(case.requirements))
    result.checks = case.run(bench)
    return result


def report_text(value: object) -> str:
    """Readable report text: hex for bytes and DTC maps, names for enums."""
    if isinstance(value, bytes):
        return value.hex(" ").upper() or "(empty)"
    if isinstance(value, dict):
        return "{" + ", ".join(f"0x{k:06X}: 0x{v:02X}" for k, v in value.items()) + "}"
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, IntEnum):
        return value.name
    if isinstance(value, (list, tuple)):
        return "(" + ", ".join(report_text(item) for item in value) + ")"
    return str(value)


def dtc_status(value: int | None) -> str | None:
    """DTC status byte as hex text, or None when the DTC is absent."""
    return None if value is None else f"0x{value:02X}"


def markdown(report: CampaignReport) -> str:
    passed = sum(case.passed for case in report.cases)
    lines = [
        f"# {report.title}",
        "",
        f"Result: {'PASSED' if report.passed else 'FAILED'} - "
        f"{passed}/{len(report.cases)} test cases passed.",
        "",
        "| Test case | Title | Requirements | Checks | Result |",
        "|---|---|---|---|---|",
    ]
    for case in report.cases:
        good = sum(check.passed for check in case.checks)
        lines.append(
            f"| {case.case_id} | {case.title} | {', '.join(case.requirements)} | "
            f"{good}/{len(case.checks)} | {'PASS' if case.passed else 'FAIL'} |"
        )
    for case in report.cases:
        lines += [
            "",
            f"## {case.case_id} {case.title}",
            "",
            "| Check | Expected | Actual | Result |",
            "|---|---|---|---|",
        ]
        for check in case.checks:
            lines.append(
                f"| {check.name} | {report_text(check.expected)} | {report_text(check.actual)} | "
                f"{'PASS' if check.passed else 'FAIL'} |"
            )
    return "\n".join(lines) + "\n"


def summary(report: CampaignReport) -> dict[str, object]:
    return {
        "title": report.title,
        "passed": report.passed,
        "cases": [
            {
                "case_id": case.case_id,
                "title": case.title,
                "requirements": case.requirements,
                "passed": case.passed,
                "checks": [
                    {
                        "name": check.name,
                        "expected": report_text(check.expected),
                        "actual": report_text(check.actual),
                        "passed": check.passed,
                    }
                    for check in case.checks
                ],
            }
            for case in report.cases
        ],
        "files": report.files,
    }


def write_artifact(path: Path, content: bytes, report: CampaignReport) -> None:
    """Write one evidence file and record its SHA-256 in the report."""
    path.write_bytes(content)
    report.files[path.name] = hashlib.sha256(content).hexdigest()


def write_reports(output: Path, report: CampaignReport) -> None:
    write_artifact(output / "report.md", markdown(report).encode("utf-8"), report)
    (output / "report.json").write_text(
        json.dumps(summary(report), indent=2) + "\n", encoding="utf-8"
    )


def print_results(cases: Sequence[CaseResult]) -> None:
    for case in cases:
        failed = [check.name for check in case.checks if not check.passed]
        mark = "PASS" if case.passed else "FAIL"
        print(f"[{mark}] {case.case_id} {case.title}" + (f" - failed: {failed}" if failed else ""))
