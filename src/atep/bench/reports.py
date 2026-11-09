"""Test reports and requirement traceability for bench test modules.

| Output | For |
|---|---|
| `canoe_xml` | A test report shaped like the CANoe/vTESTstudio XML report (module, cases, steps) |
| `junit_xml` | CI servers (Jenkins, GitHub Actions, GitLab) |
| `html_report` | People: one self-contained page with verdict colours |
| `traceability_csv` | ALM import (Codebeamer, PTC Integrity, Polarion) |
| `coverage_markdown` | Requirements verified, failing, unit-tested only or not covered |

All outputs are deterministic: times come from the bench's logical clock and a
fixed report date, never from the host clock.
"""

import csv
import html
import io
import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from atep.bench.testunit import TestCaseResult, TestModuleResult, Verdict

REPORT_DATE = datetime(2026, 1, 1, tzinfo=UTC)
REQUIREMENT_ROW = re.compile(r"^\|\s*(BENCH-(?:F|NF)-\d{3})\s*\|(.*)\|(.*)\|\s*$")


def _seconds(microseconds: int) -> str:
    return f"{microseconds / 1_000_000:.6f}"


def _xml(root: ElementTree.Element) -> str:
    ElementTree.indent(root)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        + ElementTree.tostring(root, encoding="unicode")
        + "\n"
    )


def canoe_xml(modules: Sequence[TestModuleResult], *, date: datetime = REPORT_DATE) -> str:
    """Report shaped like a CANoe test report: testmodule > testcase > teststep."""
    root = ElementTree.Element("testreport", {"starttime": date.isoformat()})
    for module in modules:
        element = ElementTree.SubElement(
            root, "testmodule", {"title": module.title, "verdict": module.verdict.label}
        )
        for case in module.cases:
            item = ElementTree.SubElement(
                element,
                "testcase",
                {
                    "ident": case.case_id,
                    "title": case.title,
                    "verdict": case.verdict.label,
                    "starttime": _seconds(case.start_us),
                    "endtime": _seconds(case.end_us),
                },
            )
            if case.requirements:
                requirements = ElementTree.SubElement(item, "requirements")
                for requirement in case.requirements:
                    ElementTree.SubElement(requirements, "requirement", {"id": requirement})
            for name, value in case.parameters.items():
                ElementTree.SubElement(item, "parameter", {"name": name, "value": str(value)})
            for step in case.steps:
                attributes = {
                    "ident": step.ident,
                    "result": step.verdict.label,
                    "timestamp": _seconds(step.timestamp_us),
                }
                if step.expected:
                    attributes["expected"] = step.expected
                if step.actual:
                    attributes["actual"] = step.actual
                ElementTree.SubElement(item, "teststep", attributes).text = step.description
    return _xml(root)


def junit_xml(modules: Sequence[TestModuleResult]) -> str:
    """JUnit XML: fail is a <failure>, error an <error>, inconclusive a <skipped>."""
    root = ElementTree.Element("testsuites")
    for module in modules:
        suite = ElementTree.SubElement(
            root,
            "testsuite",
            {
                "name": module.title,
                "tests": str(len(module.cases)),
                "failures": str(module.count(Verdict.FAIL)),
                "errors": str(module.count(Verdict.ERROR)),
                "skipped": str(module.count(Verdict.INCONCLUSIVE)),
                "time": _seconds(sum(case.end_us - case.start_us for case in module.cases)),
            },
        )
        for case in module.cases:
            item = ElementTree.SubElement(
                suite,
                "testcase",
                {
                    "classname": module.title,
                    "name": f"{case.case_id} {case.title}",
                    "time": _seconds(case.end_us - case.start_us),
                },
            )
            bad = [step for step in case.steps if step.verdict >= Verdict.INCONCLUSIVE]
            message = "; ".join(
                f"{step.description} (expected {step.expected or '-'}, got {step.actual or '-'})"
                for step in bad
            )
            if case.verdict is Verdict.ERROR:
                ElementTree.SubElement(item, "error", {"message": message})
            elif case.verdict is Verdict.FAIL:
                ElementTree.SubElement(item, "failure", {"message": message})
            elif case.verdict is Verdict.INCONCLUSIVE:
                ElementTree.SubElement(item, "skipped", {"message": message or "no verdict"})
    return _xml(root)


_COLOURS = {
    Verdict.PASS: "#1a7f37",
    Verdict.FAIL: "#cf222e",
    Verdict.ERROR: "#8250df",
    Verdict.INCONCLUSIVE: "#9a6700",
    Verdict.NONE: "#57606a",
}


def _badge(verdict: Verdict) -> str:
    return (
        f'<span style="color:#fff;background:{_COLOURS[verdict]};padding:1px 6px;'
        f'border-radius:4px">{verdict.label}</span>'
    )


def html_report(modules: Sequence[TestModuleResult], *, title: str = "Bench test report") -> str:
    escape = html.escape
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{escape(title)}</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:24px;color:#1f2328}"
        "table{border-collapse:collapse;margin:8px 0 20px}td,th{border:1px solid #d0d7de;"
        "padding:4px 8px;text-align:left;font-size:14px}th{background:#f6f8fa}</style>",
        f"</head><body><h1>{escape(title)}</h1>",
    ]
    for module in modules:
        parts.append(f"<h2>{escape(module.title)} {_badge(module.verdict)}</h2>")
        parts.append(
            "<table><tr><th>Test case</th><th>Title</th><th>Requirements</th>"
            "<th>Steps</th><th>Verdict</th></tr>"
        )
        for case in module.cases:
            parts.append(
                f"<tr><td>{escape(case.case_id)}</td><td>{escape(case.title)}</td>"
                f"<td>{escape(', '.join(case.requirements))}</td><td>{len(case.steps)}</td>"
                f"<td>{_badge(case.verdict)}</td></tr>"
            )
        parts.append("</table>")
        for case in module.cases:
            if case.verdict is Verdict.PASS:
                continue
            parts.append(
                f"<h3>{escape(case.case_id)} {escape(case.title)}</h3><table>"
                "<tr><th>Step</th><th>Expected</th><th>Actual</th><th>Verdict</th></tr>"
            )
            for step in case.steps:
                parts.append(
                    f"<tr><td>{escape(step.description)}</td><td>{escape(step.expected)}</td>"
                    f"<td>{escape(step.actual)}</td><td>{_badge(step.verdict)}</td></tr>"
                )
            parts.append("</table>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def traceability_csv(modules: Sequence[TestModuleResult]) -> str:
    """One row per requirement and test case, sorted, for import into an ALM tool."""
    rows: list[tuple[str, str, str, str, str]] = []
    for module in modules:
        for case in module.cases:
            for requirement in case.requirements:
                rows.append(
                    (requirement, case.case_id, case.title, case.verdict.label, module.title)
                )
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Requirement ID", "Test Case ID", "Test Case Title", "Verdict", "Test Module"])
    writer.writerows(sorted(rows))
    return buffer.getvalue()


class CoverageStatus(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNIT_TESTS_ONLY = "unit tests only"
    NOT_COVERED = "not covered"


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    text: str
    evidence: str


@dataclass
class RequirementCoverage:
    requirement: Requirement
    cases: list[tuple[str, Verdict]] = field(default_factory=list)

    @property
    def status(self) -> CoverageStatus:
        if self.cases:
            worst = max(verdict for _, verdict in self.cases)
            return CoverageStatus.VERIFIED if worst is Verdict.PASS else CoverageStatus.FAILED
        if "tests/" in self.requirement.evidence:
            return CoverageStatus.UNIT_TESTS_ONLY
        return CoverageStatus.NOT_COVERED


def parse_requirements(markdown: str) -> list[Requirement]:
    """Read `| ID | text | evidence |` rows from a requirements document."""
    found: list[Requirement] = []
    for line in markdown.splitlines():
        match = REQUIREMENT_ROW.match(line.strip())
        if match:
            found.append(
                Requirement(match.group(1), match.group(2).strip(), match.group(3).strip())
            )
    return found


def coverage(
    requirements: Sequence[Requirement], modules: Sequence[TestModuleResult]
) -> list[RequirementCoverage]:
    by_id = {item.requirement_id: RequirementCoverage(item) for item in requirements}
    for module in modules:
        for case in module.cases:
            for requirement in case.requirements:
                if requirement in by_id:
                    by_id[requirement].cases.append((case.case_id, case.verdict))
    return list(by_id.values())


def unknown_requirements(
    requirements: Sequence[Requirement], modules: Sequence[TestModuleResult]
) -> list[str]:
    """Requirement IDs that test cases cite but the document does not define."""
    known = {item.requirement_id for item in requirements}
    cited = {req for module in modules for case in module.cases for req in case.requirements}
    return sorted(cited - known)


def coverage_markdown(items: Sequence[RequirementCoverage], *, unknown: Sequence[str] = ()) -> str:
    counts = {
        status: sum(1 for item in items if item.status is status) for status in CoverageStatus
    }
    total = len(items) or 1
    lines = [
        "# Requirement coverage",
        "",
        f"{counts[CoverageStatus.VERIFIED]} of {len(items)} requirements are verified by passing "
        f"system-level test cases ({100 * counts[CoverageStatus.VERIFIED] / total:.0f} %).",
        "",
        "| Status | Requirements |",
        "|---|---|",
    ]
    lines += [f"| {status.value} | {counts[status]} |" for status in CoverageStatus]
    lines += ["", "| Requirement | Status | Test cases |", "|---|---|---|"]
    for item in items:
        cases = ", ".join(f"{case_id} ({verdict.label})" for case_id, verdict in item.cases)
        lines.append(
            f"| {item.requirement.requirement_id} | {item.status.value} | {cases or '-'} |"
        )
    if unknown:
        lines += [
            "",
            "Test cases cite requirements that the document does not define: " + ", ".join(unknown),
        ]
    return "\n".join(lines) + "\n"


def write_all(
    output: Path,
    modules: Sequence[TestModuleResult],
    *,
    requirements: Sequence[Requirement] = (),
    title: str = "Bench test report",
) -> dict[str, str]:
    """Write every report; returns {file name: text} for callers that hash or inspect them."""
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "test-report.xml": canoe_xml(modules),
        "junit.xml": junit_xml(modules),
        "report.html": html_report(modules, title=title),
        "traceability.csv": traceability_csv(modules),
    }
    if requirements:
        files["coverage.md"] = coverage_markdown(
            coverage(requirements, modules), unknown=unknown_requirements(requirements, modules)
        )
    for name, text in files.items():
        (output / name).write_text(text, encoding="utf-8", newline="\n")
    return files


def case_verdicts(modules: Sequence[TestModuleResult]) -> dict[str, Verdict]:
    return {case.case_id: case.verdict for module in modules for case in module.cases}


def failed_cases(modules: Sequence[TestModuleResult]) -> list[TestCaseResult]:
    return [case for module in modules for case in module.cases if case.verdict >= Verdict.FAIL]
