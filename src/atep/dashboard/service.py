from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import AiEvidenceProjection
from atep.can_network.models import CanFaultExecution, CanFrameTransmission, CanNetwork
from atep.cross_platform_automation.models import CrossPlatformAutomationReport
from atep.dashboard.schemas import (
    DashboardEvidenceCard,
    DashboardKpis,
    DashboardOverview,
    OperationalOverview,
    StatusCount,
    TestFailureDetail,
    TestFailurePage,
    TestQualityTrendPoint,
    TestQualityTrends,
)
from atep.diagnostics.models import DiagnosticCommand, DiagnosticSessionState, DiagnosticTroubleCode
from atep.ecus.models import ElectronicControlUnit
from atep.mutation_analysis.models import MutationExecution, RequirementCoverage
from atep.test_runs.models import TestCaseResult, TestRun
from atep.vehicles.models import Vehicle


async def build_operations(session: AsyncSession, *, window_hours: int) -> OperationalOverview:
    generated_at = datetime.now(UTC)
    window_start = generated_at - timedelta(hours=window_hours)
    vehicle_statuses = await _counts(
        session, select(Vehicle.status, func.count()).group_by(Vehicle.status)
    )
    ecu_states = await _counts(
        session,
        select(ElectronicControlUnit.operational_state, func.count()).group_by(
            ElectronicControlUnit.operational_state
        ),
    )
    sessions = await _counts(
        session,
        select(DiagnosticSessionState.session_type, func.count()).group_by(
            DiagnosticSessionState.session_type
        ),
    )
    dtcs = await _counts(
        session,
        select(DiagnosticTroubleCode.severity, func.count()).group_by(
            DiagnosticTroubleCode.severity
        ),
    )
    # Independent scalar subqueries avoid multiplying counts through cross-domain joins.
    totals = (
        await session.execute(
            select(
                select(func.count(CanNetwork.id)).scalar_subquery(),
                select(func.count(CanNetwork.id))
                .where(CanNetwork.can_fd_enabled.is_(True))
                .scalar_subquery(),
                select(func.count(CanFrameTransmission.id))
                .where(
                    CanFrameTransmission.created_at >= window_start,
                    CanFrameTransmission.created_at <= generated_at,
                )
                .scalar_subquery(),
                select(func.count(CanFaultExecution.id))
                .where(
                    CanFaultExecution.created_at >= window_start,
                    CanFaultExecution.created_at <= generated_at,
                )
                .scalar_subquery(),
                select(func.count(DiagnosticCommand.id))
                .where(
                    DiagnosticCommand.created_at >= window_start,
                    DiagnosticCommand.created_at <= generated_at,
                )
                .scalar_subquery(),
            )
        )
    ).one()
    return OperationalOverview(
        generated_at=generated_at,
        window_start=window_start,
        window_hours=window_hours,
        vehicle_statuses=_items(vehicle_statuses),
        ecu_states=_items(ecu_states),
        diagnostic_session_types=_items(sessions),
        stored_dtc_severities=_items(dtcs),
        can_networks_total=int(totals[0]),
        can_fd_networks_total=int(totals[1]),
        can_transmissions_total=int(totals[2]),
        can_fault_executions_total=int(totals[3]),
        diagnostic_commands_total=int(totals[4]),
        limitations=[
            "Inventory, ECU states, sessions and stored DTCs are current records, not live health.",
            "Activity counts use server creation timestamps within the selected UTC window.",
            "Stored DTCs need not be active faults; fault executions include recovery.",
            "Sequential queries can observe concurrent changes; this is not an atomic snapshot.",
        ],
    )


async def _counts(session: AsyncSession, statement: Select[tuple[str, int]]) -> dict[str, int]:
    rows = (await session.execute(statement)).all()
    return {str(name): int(count) for name, count in rows}


def _items(values: dict[str, int]) -> list[StatusCount]:
    return [StatusCount(status=name, count=count) for name, count in sorted(values.items())]


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator * 100 / denominator, 2) if denominator else None


def _day_start(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def quality_trends_from_rows(
    *,
    generated_at: datetime,
    window_days: int,
    run_rows: Sequence[tuple[datetime, str, int]],
    case_rows: Sequence[tuple[datetime, str, int]],
) -> TestQualityTrends:
    last_day = _day_start(generated_at)
    window_start = last_day - timedelta(days=window_days - 1)
    values: dict[datetime, dict[str, dict[str, int]]] = {}
    for index in range(window_days):
        values[window_start + timedelta(days=index)] = {"runs": {}, "cases": {}}
    for bucket, status, count in run_rows:
        day = _day_start(bucket)
        if day in values:
            values[day]["runs"][status] = int(count)
    for bucket, status, count in case_rows:
        day = _day_start(bucket)
        if day in values:
            values[day]["cases"][status] = int(count)
    points: list[TestQualityTrendPoint] = []
    for bucket, groups in values.items():
        runs = groups["runs"]
        cases = groups["cases"]
        case_total = sum(cases.values())
        points.append(
            TestQualityTrendPoint(
                bucket_start=bucket,
                test_runs_total=sum(runs.values()),
                test_runs_passed=runs.get("passed", 0),
                test_runs_failed=runs.get("failed", 0),
                test_cases_total=case_total,
                test_cases_passed=cases.get("passed", 0),
                test_cases_failed=cases.get("failed", 0),
                test_case_pass_rate=_rate(cases.get("passed", 0), case_total),
            )
        )
    return TestQualityTrends(
        generated_at=generated_at,
        window_start=window_start,
        window_days=window_days,
        points=points,
        limitations=[
            "Buckets use UTC calendar days and recorded lifecycle timestamps.",
            "Historical trends describe recorded test evidence and do not infer certification.",
        ],
    )


async def build_quality_trends(session: AsyncSession, *, window_days: int) -> TestQualityTrends:
    generated_at = datetime.now(UTC)
    window_start = _day_start(generated_at) - timedelta(days=window_days - 1)
    run_day = func.date_trunc("day", TestRun.created_at)
    run_rows = (
        await session.execute(
            select(run_day, TestRun.status, func.count())
            .where(TestRun.created_at >= window_start)
            .group_by(run_day, TestRun.status)
        )
    ).all()
    case_day = func.date_trunc("day", TestCaseResult.updated_at)
    case_rows = (
        await session.execute(
            select(case_day, TestCaseResult.status, func.count())
            .where(TestCaseResult.updated_at >= window_start)
            .group_by(case_day, TestCaseResult.status)
        )
    ).all()
    return quality_trends_from_rows(
        generated_at=generated_at,
        window_days=window_days,
        run_rows=cast(Sequence[tuple[datetime, str, int]], run_rows),
        case_rows=cast(Sequence[tuple[datetime, str, int]], case_rows),
    )


async def list_test_failures(
    session: AsyncSession,
    *,
    window_hours: int,
    suite: str | None,
    limit: int,
    offset: int,
) -> TestFailurePage:
    window_start = datetime.now(UTC) - timedelta(hours=window_hours)
    filters = [TestCaseResult.status == "failed", TestCaseResult.updated_at >= window_start]
    if suite is not None:
        filters.append(TestRun.suite == suite)
    total = int(
        await session.scalar(
            select(func.count(TestCaseResult.id))
            .join(TestRun, TestRun.id == TestCaseResult.test_run_id)
            .where(*filters)
        )
        or 0
    )
    rows = (
        await session.execute(
            select(TestCaseResult, TestRun)
            .join(TestRun, TestRun.id == TestCaseResult.test_run_id)
            .where(*filters)
            .order_by(TestCaseResult.updated_at.desc(), TestCaseResult.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    items: list[TestFailureDetail] = []
    for result, run in rows:
        observation = result.observed
        items.append(
            TestFailureDetail(
                result_id=str(result.id),
                test_run_id=str(run.id),
                run_id=run.run_id,
                case_id=result.case_id,
                definition_id=result.definition_id,
                suite=run.suite,
                attempt=result.attempt,
                duration_ms=result.duration_ms,
                observation=observation[:500] if observation is not None else None,
                observation_truncated=observation is not None and len(observation) > 500,
                evidence_refs=list(result.evidence_refs),
                failed_at=result.updated_at,
            )
        )
    return TestFailurePage(items=items, total=total, limit=limit, offset=offset)


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
