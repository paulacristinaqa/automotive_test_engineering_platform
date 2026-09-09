from dataclasses import dataclass
from typing import Any, Protocol

from atep.ai_engine.schemas import AiAnalysisResult, AiFinding

LOCAL_RULE_VERSION = "local-rules-v1"


class AnalysisAdapter(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def provider_kind(self) -> str: ...

    @property
    def version(self) -> str: ...

    def analyze(
        self,
        *,
        task: str,
        context: dict[str, Any],
        evidence_refs: list[str],
    ) -> AiAnalysisResult: ...


@dataclass(frozen=True)
class LocalRuleAdapter:
    provider_id: str = "local-rules"
    provider_kind: str = "local"
    version: str = LOCAL_RULE_VERSION

    def analyze(
        self,
        *,
        task: str,
        context: dict[str, Any],
        evidence_refs: list[str],
    ) -> AiAnalysisResult:
        findings: list[AiFinding] = []
        dtc_codes = _string_list(context.get("dtc_codes"))
        if dtc_codes:
            findings.append(
                AiFinding(
                    code="DTC_PRESENT",
                    severity="high",
                    message=(
                        f"The supplied context contains {len(dtc_codes)} "
                        "diagnostic trouble code(s)."
                    ),
                    evidence_refs=evidence_refs[:10],
                )
            )
        failure_count = context.get("failure_count")
        if (
            isinstance(failure_count, int)
            and not isinstance(failure_count, bool)
            and failure_count > 0
        ):
            findings.append(
                AiFinding(
                    code="FAILURES_REPORTED",
                    severity="high",
                    message=f"The supplied context reports {failure_count} failure(s).",
                    evidence_refs=evidence_refs[:10],
                )
            )
        failed_thresholds = _string_list(context.get("failed_thresholds"))
        if failed_thresholds:
            findings.append(
                AiFinding(
                    code="THRESHOLDS_FAILED",
                    severity="medium",
                    message=(
                        f"The supplied context reports {len(failed_thresholds)} "
                        "failed threshold(s)."
                    ),
                    evidence_refs=evidence_refs[:10],
                )
            )
        if not findings:
            findings.append(
                AiFinding(
                    code="NO_RULE_MATCH",
                    severity="info",
                    message="No deterministic local rule matched the supplied structured context.",
                    evidence_refs=evidence_refs[:10],
                )
            )
        recommendations = _recommendations(task, findings)
        matched = sum(item.code != "NO_RULE_MATCH" for item in findings)
        return AiAnalysisResult(
            summary=(
                f"Deterministic {task.replace('_', ' ')} completed with {matched} matched rule(s)."
            ),
            findings=findings,
            recommendations=recommendations,
            confidence=0.8 if matched else 0.25,
        )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _recommendations(task: str, findings: list[AiFinding]) -> list[str]:
    codes = {item.code for item in findings}
    recommendations = ["Review the cited evidence before accepting any advisory conclusion."]
    if "DTC_PRESENT" in codes:
        recommendations.append(
            "Correlate each supplied DTC with ECU state and its occurrence timeline."
        )
    if "FAILURES_REPORTED" in codes:
        recommendations.append(
            "Compare failed cases with the latest successful regression baseline."
        )
    if "THRESHOLDS_FAILED" in codes:
        recommendations.append("Review the measured values against the stored performance profile.")
    if task == "test_suggestion":
        recommendations.append(
            "Create suggestions as drafts and require human review before promotion."
        )
    return recommendations


ADAPTERS: dict[str, AnalysisAdapter] = {"local-rules": LocalRuleAdapter()}
