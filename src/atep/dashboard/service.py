from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import AiEvidenceProjection
from atep.cross_platform_automation.models import CrossPlatformAutomationReport
from atep.dashboard.schemas import (
    DashboardEvidenceCard,
    DashboardKpis,
    DashboardOverview,
    StatusCount,
)
from atep.mutation_analysis.models import MutationExecution, RequirementCoverage
from atep.test_runs.models import TestCaseResult, TestRun


async def _counts(session: AsyncSession, statement: Select[tuple[str, int]]) -> dict[str, int]:
    rows = (await session.execute(statement)).all()
    return {str(name): int(count) for name, count in rows}


def _items(values: dict[str, int]) -> list[StatusCount]:
    return [StatusCount(status=name, count=count) for name, count in sorted(values.items())]


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator * 100 / denominator, 2) if denominator else None


async def build_overview(
    session: AsyncSession, *, window_hours: int, evidence_limit: int
) -> DashboardOverview:
    generated_at = datetime.now(UTC)
    window_start = generated_at - timedelta(hours=window_hours)

    run_statuses = await _counts(
        session,
        select(TestRun.status, func.count())
        .where(TestRun.created_at >= window_start)
        .group_by(TestRun.status),
    )
    case_statuses = await _counts(
        session,
        select(TestCaseResult.status, func.count())
        .join(TestRun, TestRun.id == TestCaseResult.test_run_id)
        .where(TestRun.created_at >= window_start)
        .group_by(TestCaseResult.status),
    )
    requirement_statuses = await _counts(
        session,
        select(RequirementCoverage.status, func.count()).group_by(RequirementCoverage.status),
    )
    automation_outcomes = await _counts(
        session,
        select(CrossPlatformAutomationReport.outcome, func.count())
        .where(CrossPlatformAutomationReport.created_at >= window_start)
        .group_by(CrossPlatformAutomationReport.outcome),
    )
    evidence_severities = await _counts(
        session,
        select(AiEvidenceProjection.severity, func.count())
        .where(
            AiEvidenceProjection.consumer == "dashboard",
            AiEvidenceProjection.created_at >= window_start,
        )
        .group_by(AiEvidenceProjection.severity),
    )
    mutation_count, average_score = (
        await session.execute(
            select(
                func.count(MutationExecution.id), func.avg(MutationExecution.mutation_score)
            ).where(MutationExecution.created_at >= window_start)
        )
    ).one()
    evidence: Sequence[AiEvidenceProjection] = (
        (
            await session.scalars(
                select(AiEvidenceProjection)
                .where(
                    AiEvidenceProjection.consumer == "dashboard",
                    AiEvidenceProjection.created_at >= window_start,
                )
                .order_by(AiEvidenceProjection.created_at.desc(), AiEvidenceProjection.id.desc())
                .limit(evidence_limit)
            )
        )
        .unique()
        .all()
    )

    run_total = sum(run_statuses.values())
    case_total = sum(case_statuses.values())
    requirement_total = sum(requirement_statuses.values())
    requirement_covered = requirement_statuses.get("covered", 0)
    return DashboardOverview(
        generated_at=generated_at,
        window_start=window_start,
        window_hours=window_hours,
        kpis=DashboardKpis(
            test_runs_total=run_total,
            active_test_runs=run_statuses.get("queued", 0) + run_statuses.get("running", 0),
            test_cases_total=case_total,
            test_cases_passed=case_statuses.get("passed", 0),
            test_cases_failed=case_statuses.get("failed", 0),
            test_case_pass_rate=_rate(case_statuses.get("passed", 0), case_total),
            requirements_total=requirement_total,
            requirements_covered=requirement_covered,
            requirement_coverage_rate=_rate(requirement_covered, requirement_total),
            mutation_executions_total=int(mutation_count or 0),
            average_mutation_score=round(float(average_score), 2)
            if average_score is not None
            else None,
            automation_reports_total=sum(automation_outcomes.values()),
            dashboard_ai_evidence_total=sum(evidence_severities.values()),
        ),
        test_run_statuses=_items(run_statuses),
        test_case_statuses=_items(case_statuses),
        requirement_statuses=_items(requirement_statuses),
        automation_outcomes=_items(automation_outcomes),
        ai_evidence_severities=_items(evidence_severities),
        evidence_cards=[
            DashboardEvidenceCard(
                projection_id=item.projection_id,
                subject_type=item.subject_type,
                subject_id=item.subject_id,
                status=item.status,
                severity=item.severity,
                headline=item.headline,
                summary=item.summary,
                citations=list(item.citations),
                created_at=item.created_at,
            )
            for item in evidence
        ],
        limitations=[
            (
                "Execution KPIs use the selected time window; requirement coverage is the "
                "current snapshot."
            ),
            "This read model summarizes recorded evidence and does not infer safety certification.",
        ],
    )
