import json
from pathlib import Path

import pytest

from atep.bench.airbag import ACU_SOFTWARE_VERSION
from atep.bench.reports import CoverageStatus, Requirement, RequirementCoverage
from atep.bench.testunit import StepResult, TestCaseResult, TestModuleResult, Verdict
from tools.run_acu_system_test import (
    SAFETY_REQUIREMENTS,
    VARIANTS,
    catalogue_markdown,
    draft_defects,
    evaluate_exit_criteria,
    identify_environment,
    identify_test_object,
    main,
    run_system_test,
)


def _case(
    case_id: str, verdict: Verdict, requirements: list[str], step: str = "check"
) -> TestCaseResult:
    return TestCaseResult(
        case_id,
        f"title {case_id}",
        requirements,
        [StepResult("1", step, verdict, 0, expected="1", actual="2")],
    )


def _covered(requirement_id: str, status_verdict: Verdict) -> RequirementCoverage:
    item = RequirementCoverage(Requirement(requirement_id, "text", "evidence"))
    item.cases.append(("X", status_verdict))
    return item


def test_exit_criteria_all_met_for_a_clean_run() -> None:
    module = TestModuleResult(
        "m",
        [
            _case("A", Verdict.PASS, ["BENCH-F-029"], "No unintended deployment"),
            _case("B", Verdict.PASS, ["BENCH-F-001"], "Functional status class"),
        ],
    )
    criteria = evaluate_exit_criteria([module], [_covered("BENCH-F-029", Verdict.PASS)])
    assert [criterion.met for criterion in criteria] == [True] * 6
    assert [criterion.ident for criterion in criteria] == [f"EC-{n}" for n in range(1, 7)]


def test_exit_criteria_name_what_is_missing() -> None:
    module = TestModuleResult(
        "m",
        [
            _case("A", Verdict.FAIL, ["BENCH-F-029"], "No unintended deployment"),
            _case("B", Verdict.ERROR, ["BENCH-F-001"]),
            _case("C", Verdict.INCONCLUSIVE, []),
        ],
    )
    gap = RequirementCoverage(Requirement("BENCH-F-999", "text", "review"))
    criteria = {c.ident: c for c in evaluate_exit_criteria([module], [gap])}
    assert not criteria["EC-1"].met and "B, C" in criteria["EC-1"].detail
    assert not criteria["EC-2"].met and "0/3 passed" in criteria["EC-2"].detail
    assert gap.status is CoverageStatus.NOT_COVERED and "BENCH-F-999" in criteria["EC-3"].detail
    assert not criteria["EC-4"].met and "A" in criteria["EC-4"].detail
    assert not criteria["EC-5"].met
    assert not criteria["EC-6"].met  # no EMC class check ran at all


def test_defect_drafts_rate_safety_failures_high() -> None:
    module = TestModuleResult(
        "m",
        [
            _case("A", Verdict.PASS, ["BENCH-F-029"]),
            _case("B", Verdict.FAIL, ["BENCH-F-029"]),
            _case("C", Verdict.ERROR, ["BENCH-F-040"]),
        ],
    )
    drafts = draft_defects([module])
    assert [(d.ident, d.test_case, d.severity) for d in drafts] == [
        ("DEF-001", "B", "High (safety-related)"),
        ("DEF-002", "C", "Medium"),
    ]
    assert drafts[0].failed_steps == ("check: expected 1, got 2",)
    assert "BENCH-F-029" in SAFETY_REQUIREMENTS


def test_test_object_and_environment_identification() -> None:
    baseline = identify_test_object(VARIANTS["baseline"])
    defective = identify_test_object(VARIANTS["no-firing-inhibit"])
    assert baseline.software_version == ACU_SOFTWARE_VERSION
    assert baseline.vin == "WATEP000000000001"
    assert baseline.calibration_sha256 != defective.calibration_sha256
    assert baseline.dbc_sha256 == defective.dbc_sha256
    environment = identify_environment()
    assert environment["TRG"].startswith("ATEP,VIRTUAL-TRANSIENT-GEN")
    assert set(environment) >= {"PSU", "REL", "FIB", "DMM", "CHAM", "Python", "python-can"}


def test_catalogue_lists_every_case() -> None:
    module = TestModuleResult(
        "m", [_case("A", Verdict.PASS, ["R1", "R2"]), _case("B", Verdict.FAIL, [])]
    )
    text = catalogue_markdown([module])
    assert "| m | A | title A | R1, R2 | pass |" in text
    assert "| m | B | title B | - | fail |" in text


def test_baseline_release_is_recommended_with_complete_evidence(tmp_path: Path) -> None:
    result = run_system_test(tmp_path, revision="test")
    assert result.release_recommended, [c for c in result.criteria if not c.met]
    assert result.defects == []
    assert sum(len(module.cases) for module in result.modules) == 53
    expected = {
        "test-summary-report.md",
        "test-summary.json",
        "test-catalogue.md",
        "test-report.xml",
        "junit.xml",
        "report.html",
        "traceability.csv",
        "coverage.md",
        "evidence/acu/acu.dbc",
        "evidence/hil/scpi-log.txt",
        "evidence/emc/emc-test-plan.md",
    }
    assert expected <= set(result.manifest)
    manifest = json.loads((tmp_path / "evidence-manifest.json").read_text(encoding="utf-8"))
    assert manifest == result.manifest
    summary = (tmp_path / "test-summary-report.md").read_text(encoding="utf-8")
    assert "RELEASE RECOMMENDED" in summary and "No defects found." in summary
    assert "| ATEP revision | test |" in summary


@pytest.mark.parametrize(
    ("variant", "failing_case", "safety"),
    [
        ("short-supply-debounce", "HIL-T06", False),
        ("no-firing-inhibit", "EMC-T05", True),
        ("high-airbag-threshold", "ACU-T08", True),
    ],
)
def test_seeded_defects_block_the_release(
    tmp_path: Path, variant: str, failing_case: str, safety: bool
) -> None:
    result = run_system_test(tmp_path, variant=variant, revision="test")
    assert not result.release_recommended
    defect = next(d for d in result.defects if d.test_case == failing_case)
    assert defect.severity.startswith("High") is safety
    criteria = {c.ident: c.met for c in result.criteria}
    assert criteria["EC-2"] is False and criteria["EC-4"] is (not safety)
    summary = json.loads((tmp_path / "test-summary.json").read_text(encoding="utf-8"))
    assert summary["release_recommended"] is False


def test_evidence_is_reproducible(tmp_path: Path) -> None:
    first = run_system_test(tmp_path / "a", revision="test").manifest
    second = run_system_test(tmp_path / "b", revision="test").manifest
    assert first == second


def test_cli_exit_codes(tmp_path: Path) -> None:
    assert main(["--output", str(tmp_path / "ok"), "--revision", "test"]) == 0
    assert (
        main(
            [
                "--output",
                str(tmp_path / "bad"),
                "--revision",
                "test",
                "--variant",
                "no-firing-inhibit",
            ]
        )
        == 1
    )
