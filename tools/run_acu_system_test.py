"""ACU system test (Volume XI-7): execute, evaluate exit criteria, recommend a release.

This is the run described in docs/acu-system-test-plan.md. It identifies the test
object and the bench, runs every test definition from
docs/acu-system-test-specification.md, evaluates the exit criteria, drafts a
defect for every failing test case, and writes a test summary report with an
evidence manifest (SHA-256 of every file).

Seeded-defect variants show that the campaign detects regressions:

    python tools/run_acu_system_test.py --output out/acu-system-test
    python tools/run_acu_system_test.py --variant no-firing-inhibit --output out/defective
"""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from importlib.metadata import version
from pathlib import Path

from atep.bench.airbag import AcuCalibration, airbag_network_spec
from atep.bench.airbag_bench import HilBench
from atep.bench.reports import (
    CoverageStatus,
    RequirementCoverage,
    coverage,
    parse_requirements,
    write_all,
)
from atep.bench.testunit import TestCaseResult, TestModuleResult, Verdict
from atep.bench.vector_dbc import render_dbc
from tools.run_test_units_demo import REQUIREMENTS, run_modules

# Requirements whose failure could cause or hide a wrong deployment decision.
SAFETY_REQUIREMENTS = frozenset(
    {
        "BENCH-F-029",
        "BENCH-F-030",
        "BENCH-F-031",
        "BENCH-F-032",
        "BENCH-F-033",
        "BENCH-F-046",
        "BENCH-NF-015",
    }
)


@dataclass(frozen=True)
class Variant:
    name: str
    description: str
    calibration: AcuCalibration


VARIANTS = {
    variant.name: variant
    for variant in (
        Variant("baseline", "Release candidate calibration", AcuCalibration()),
        Variant(
            "short-supply-debounce",
            "Seeded defect: supply DTC debounce shortened to 500 ms",
            AcuCalibration(supply_debounce_us=500_000),
        ),
        Variant(
            "no-firing-inhibit",
            "Seeded defect: firing inhibit level above the 33 V input clamp",
            AcuCalibration(firing_inhibit_v=40.0),
        ),
        Variant(
            "high-airbag-threshold",
            "Seeded defect: airbag threshold raised to 30 km/h",
            AcuCalibration(airbag_threshold_kmh=30.0),
        ),
    )
}


@dataclass(frozen=True)
class TestObject:
    name: str
    variant: str
    description: str
    software_version: str
    vin: str
    calibration_sha256: str
    dbc_sha256: str

    __test__ = False


@dataclass(frozen=True)
class ExitCriterion:
    ident: str
    description: str
    met: bool
    detail: str


@dataclass(frozen=True)
class DefectDraft:
    ident: str
    title: str
    severity: str
    test_case: str
    requirements: tuple[str, ...]
    failed_steps: tuple[str, ...]


@dataclass
class SystemTestResult:
    test_object: TestObject
    environment: dict[str, str]
    modules: list[TestModuleResult]
    criteria: list[ExitCriterion]
    defects: list[DefectDraft]
    manifest: dict[str, str] = field(default_factory=dict)

    @property
    def release_recommended(self) -> bool:
        return all(criterion.met for criterion in self.criteria)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identify_test_object(variant: Variant) -> TestObject:
    """Read identification DIDs from the ACU itself and fingerprint its configuration."""
    bench = HilBench(calibration=variant.calibration)
    bench.switch_on()
    software = bench.ask("22F195").response[3:].decode("ascii")
    vin = bench.ask("22F190").response[3:].decode("ascii")
    calibration = json.dumps(asdict(variant.calibration), sort_keys=True).encode()
    return TestObject(
        name="Virtual airbag control unit",
        variant=variant.name,
        description=variant.description,
        software_version=software,
        vin=vin,
        calibration_sha256=_sha256(calibration),
        dbc_sha256=_sha256(render_dbc(airbag_network_spec()).encode()),
    )


def identify_environment() -> dict[str, str]:
    bench = HilBench()
    environment = {
        address: bench.scpi(address, "*IDN?") or "no answer"
        for address in ("PSU", "REL", "FIB", "DMM", "CHAM", "TRG")
    }
    environment["Bus"] = "SimulatedLink, classic CAN 500 kbit/s, logical time"
    environment["Python"] = platform.python_version()
    environment["python-can"] = version("python-can")
    return environment


def _cases(modules: list[TestModuleResult]) -> list[TestCaseResult]:
    return [case for module in modules for case in module.cases]


def _steps_named(modules: list[TestModuleResult], name: str) -> list[Verdict]:
    return [
        step.verdict for case in _cases(modules) for step in case.steps if step.description == name
    ]


def evaluate_exit_criteria(
    modules: list[TestModuleResult], items: list[RequirementCoverage]
) -> list[ExitCriterion]:
    cases = _cases(modules)
    unfinished = [c.case_id for c in cases if c.verdict in {Verdict.ERROR, Verdict.INCONCLUSIVE}]
    failed = [c.case_id for c in cases if c.verdict is not Verdict.PASS]
    gaps = [
        item.requirement.requirement_id
        for item in items
        if item.status in {CoverageStatus.FAILED, CoverageStatus.NOT_COVERED}
    ]
    safety = [
        case.case_id
        for case in cases
        if SAFETY_REQUIREMENTS & set(case.requirements) and case.verdict is not Verdict.PASS
    ]
    deployment = _steps_named(modules, "No unintended deployment")
    classes = _steps_named(modules, "Functional status class")

    def listing(items_: list[str]) -> str:
        return ", ".join(items_) if items_ else "none"

    return [
        ExitCriterion(
            "EC-1",
            "Every test case executed to a verdict (no error, no inconclusive)",
            not unfinished,
            f"{len(cases) - len(unfinished)}/{len(cases)} executed; "
            f"unfinished: {listing(unfinished)}",
        ),
        ExitCriterion(
            "EC-2",
            "Every test case passed",
            not failed,
            f"{len(cases) - len(failed)}/{len(cases)} passed; not passed: {listing(failed)}",
        ),
        ExitCriterion(
            "EC-3",
            "Every requirement verified by a passing system test or by unit tests",
            not gaps,
            f"failed or uncovered requirements: {listing(gaps)}",
        ),
        ExitCriterion(
            "EC-4",
            "Every test case of a safety-related requirement passed",
            not safety,
            f"failing safety-related cases: {listing(safety)}",
        ),
        ExitCriterion(
            "EC-5",
            "No unintended deployment in any EMC test",
            bool(deployment) and all(v is Verdict.PASS for v in deployment),
            f"{deployment.count(Verdict.PASS)}/{len(deployment)} checks passed",
        ),
        ExitCriterion(
            "EC-6",
            "Every EMC test reached its required functional status class",
            bool(classes) and all(v is Verdict.PASS for v in classes),
            f"{classes.count(Verdict.PASS)}/{len(classes)} classes met",
        ),
    ]


def draft_defects(modules: list[TestModuleResult]) -> list[DefectDraft]:
    """One defect draft per failing test case, ready to copy into an issue tracker."""
    drafts: list[DefectDraft] = []
    for case in _cases(modules):
        if case.verdict is Verdict.PASS:
            continue
        steps = tuple(
            f"{step.description}: expected {step.expected or '-'}, got {step.actual or '-'}"
            for step in case.steps
            if step.verdict is not Verdict.PASS
        )
        safety = bool(SAFETY_REQUIREMENTS & set(case.requirements))
        drafts.append(
            DefectDraft(
                ident=f"DEF-{len(drafts) + 1:03d}",
                title=f"{case.case_id} {case.title}: {case.verdict.label}",
                severity="High (safety-related)" if safety else "Medium",
                test_case=case.case_id,
                requirements=tuple(case.requirements),
                failed_steps=steps,
            )
        )
    return drafts


def catalogue_markdown(modules: list[TestModuleResult]) -> str:
    lines = [
        "# ACU system test catalogue",
        "",
        "| Module | Test case | Title | Requirements | Verdict |",
        "|---|---|---|---|---|",
    ]
    for module in modules:
        for case in module.cases:
            lines.append(
                f"| {module.title} | {case.case_id} | {case.title} | "
                f"{', '.join(case.requirements) or '-'} | {case.verdict.label} |"
            )
    return "\n".join(lines) + "\n"


def summary_markdown(result: SystemTestResult, revision: str) -> str:
    test_object = result.test_object
    cases = _cases(result.modules)
    recommended = result.release_recommended
    lines = [
        "# ACU system test summary report",
        "",
        f"**Release recommendation: {'RELEASE RECOMMENDED' if recommended else 'NOT RECOMMENDED'}**"
        f" - {sum(c.verdict is Verdict.PASS for c in cases)}/{len(cases)} test cases passed, "
        f"{sum(c.met for c in result.criteria)}/{len(result.criteria)} exit criteria met.",
        "",
        "## Test object",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Device | {test_object.name} |",
        f"| Variant | {test_object.variant} ({test_object.description}) |",
        f"| Software version (DID F195) | {test_object.software_version} |",
        f"| VIN (DID F190) | {test_object.vin} |",
        f"| Calibration SHA-256 | `{test_object.calibration_sha256[:16]}` |",
        f"| CAN database SHA-256 | `{test_object.dbc_sha256[:16]}` |",
        f"| ATEP revision | {revision} |",
        "",
        "## Test environment",
        "",
        "| Item | Identification |",
        "|---|---|",
        *[f"| {key} | {value} |" for key, value in result.environment.items()],
        "",
        "## Results by test module",
        "",
        "| Module | Cases | Passed | Failed | Error | Inconclusive | Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for module in result.modules:
        lines.append(
            f"| {module.title} | {len(module.cases)} | {module.count(Verdict.PASS)} | "
            f"{module.count(Verdict.FAIL)} | {module.count(Verdict.ERROR)} | "
            f"{module.count(Verdict.INCONCLUSIVE)} | {module.verdict.label} |"
        )
    lines += ["", "## Exit criteria", "", "| ID | Criterion | Met | Detail |", "|---|---|---|---|"]
    lines += [
        f"| {c.ident} | {c.description} | {'yes' if c.met else 'NO'} | {c.detail} |"
        for c in result.criteria
    ]
    lines += ["", "## Defects", ""]
    if result.defects:
        lines += [
            "| ID | Severity | Test case | Requirements | Failed steps |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {d.ident} | {d.severity} | {d.test_case} | {', '.join(d.requirements) or '-'} | "
            f"{'<br>'.join(d.failed_steps) or '-'} |"
            for d in result.defects
        ]
    else:
        lines.append("No defects found.")
    lines += [
        "",
        "## Evidence",
        "",
        "Detailed results are in `test-report.xml`, `junit.xml`, `report.html`, "
        "`traceability.csv`, `coverage.md` and `test-catalogue.md`; campaign artifacts "
        "(traces, DBC, SCPI log, EMC test plan) are under `evidence/`. "
        "`evidence-manifest.json` lists the SHA-256 of every file.",
    ]
    return "\n".join(lines) + "\n"


def write_manifest(output: Path) -> dict[str, str]:
    manifest = {
        path.relative_to(output).as_posix(): _sha256(path.read_bytes())
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "evidence-manifest.json"
    }
    (output / "evidence-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def run_system_test(
    output: Path, *, variant: str = "baseline", revision: str = "unversioned"
) -> SystemTestResult:
    selected = VARIANTS[variant]
    output.mkdir(parents=True, exist_ok=True)
    modules = run_modules(output / "evidence", selected.calibration)
    requirements = parse_requirements(REQUIREMENTS.read_text(encoding="utf-8"))
    items = coverage(requirements, modules)
    write_all(output, modules, requirements=requirements, title="ACU system test report")
    result = SystemTestResult(
        test_object=identify_test_object(selected),
        environment=identify_environment(),
        modules=modules,
        criteria=evaluate_exit_criteria(modules, items),
        defects=draft_defects(modules),
    )
    (output / "test-catalogue.md").write_text(catalogue_markdown(modules), encoding="utf-8")
    (output / "test-summary-report.md").write_text(
        summary_markdown(result, revision), encoding="utf-8"
    )
    summary = {
        "release_recommended": result.release_recommended,
        "test_object": asdict(result.test_object),
        "revision": revision,
        "exit_criteria": [asdict(criterion) for criterion in result.criteria],
        "defects": [asdict(defect) for defect in result.defects],
    }
    (output / "test-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    result.manifest = write_manifest(output)
    return result


def _git_revision() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unversioned"
    return completed.stdout.strip() or "unversioned"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ATEP Volume XI-7 ACU system test")
    parser.add_argument("--output", type=Path, default=Path("out/acu-system-test"))
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="baseline")
    parser.add_argument("--revision", default=None, help="ATEP revision to record (default: git)")
    args = parser.parse_args(argv)
    result = run_system_test(
        args.output, variant=args.variant, revision=args.revision or _git_revision()
    )
    for criterion in result.criteria:
        print(
            f"[{'MET' if criterion.met else 'NOT MET'}] {criterion.ident} {criterion.description}"
        )
    for defect in result.defects:
        print(f"  {defect.ident} {defect.severity}: {defect.title}")
    verdict = "RELEASE RECOMMENDED" if result.release_recommended else "NOT RECOMMENDED"
    print(f"{verdict}; summary in {args.output / 'test-summary-report.md'}")
    return 0 if result.release_recommended else 1


if __name__ == "__main__":
    sys.exit(main())
