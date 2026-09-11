"""Supporting evidence only: no inferred OTA readiness or standards conformity."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.dashboard.schemas import StatusCount
from atep.diagnostics.models import DiagnosticFlashState
from atep.mutation_analysis.models import RequirementCoverage


class EvidenceGap(BaseModel):
    area: Literal["ota", "cybersecurity", "aspice", "iso26262"]
    status: Literal["not_implemented", "not_assessed"]
    supporting_sources: list[str]
    missing_capabilities: list[str]
    limitation: str


class EvidenceReadiness(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_hours: int = Field(ge=1, le=720)
    diagnostic_flash_states: list[StatusCount]
    requirement_coverage_states: list[StatusCount]
    audit_outcomes: list[StatusCount]
    gaps: list[EvidenceGap]
    assessment: Literal["not_assessed"] = "not_assessed"
    contract_version: Literal["dashboard-evidence-gaps-v1"] = "dashboard-evidence-gaps-v1"
    limitations: list[str]


def evidence_gaps() -> list[EvidenceGap]:
    return [
        EvidenceGap(
            area="ota",
            status="not_implemented",
            supporting_sources=["diagnostic_flash_states"],
            missing_capabilities=["OTA campaign lifecycle and delivery evidence"],
            limitation="Diagnostic ECU flashing is not OTA delivery or rollout evidence.",
        ),
        EvidenceGap(
            area="cybersecurity",
            status="not_assessed",
            supporting_sources=["audit_records", "docs/software-supply-chain-security.md"],
            missing_capabilities=[
                "Formal automotive cybersecurity assessment and evidence mapping"
            ],
            limitation="Administrative audit outcomes are not attack or vulnerability counts.",
        ),
        EvidenceGap(
            area="aspice",
            status="not_assessed",
            supporting_sources=["requirement_coverage"],
            missing_capabilities=[
                "Reviewed process assessment and standards-specific evidence mapping"
            ],
            limitation="Generic requirement coverage does not establish process capability.",
        ),
        EvidenceGap(
            area="iso26262",
            status="not_assessed",
            supporting_sources=["requirement_coverage"],
            missing_capabilities=["Reviewed functional safety assessment and evidence mapping"],
            limitation="Test coverage establishes neither safety conformity nor certification.",
        ),
    ]


async def build_evidence_readiness(
    session: AsyncSession, *, window_hours: int
) -> EvidenceReadiness:
    now = datetime.now(UTC)
    start = now - timedelta(hours=window_hours)
    statements = [
        select(DiagnosticFlashState.status, func.count())
        .group_by(DiagnosticFlashState.status)
        .order_by(DiagnosticFlashState.status),
        select(RequirementCoverage.status, func.count())
        .group_by(RequirementCoverage.status)
        .order_by(RequirementCoverage.status),
        select(AuditRecord.outcome, func.count())
        .where(AuditRecord.created_at >= start, AuditRecord.created_at <= now)
        .group_by(AuditRecord.outcome)
        .order_by(AuditRecord.outcome),
    ]
    groups = []
    for statement in statements:
        groups.append(
            [
                StatusCount(status=status, count=count)
                for status, count in (await session.execute(statement)).all()
            ]
        )
    return EvidenceReadiness(
        generated_at=now,
        window_start=start,
        window_hours=window_hours,
        diagnostic_flash_states=groups[0],
        requirement_coverage_states=groups[1],
        audit_outcomes=groups[2],
        gaps=evidence_gaps(),
        limitations=[
            "Flash and coverage are current stored states; audit outcomes use the UTC window.",
            "Source references identify supporting data, not verified standards evidence.",
            "Gaps are a versioned implementation inventory, not an automated assessment.",
            "Sequential reads are not an atomic snapshot; no readiness percentage is inferred.",
        ],
    )
