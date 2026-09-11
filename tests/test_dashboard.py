from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import AiEvidenceProjection
from atep.dashboard.service import (
    build_operations,
    build_overview,
    list_test_failures,
    quality_trends_from_rows,
)
from atep.identity.permissions import PermissionName
from atep.test_runs.models import TestCaseResult as CaseResultModel
from atep.test_runs.models import TestRun as RunModel


class ExecuteResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def all(self) -> list[tuple[str, int]]:
        return cast(list[tuple[str, int]], self.value)

    def one(self) -> tuple[int, float | None]:
        return cast(tuple[int, float | None], self.value)


class ScalarResult:
    def __init__(self, values: list[AiEvidenceProjection]) -> None:
        self.values = values

    def unique(self) -> "ScalarResult":
        return self

    def all(self) -> list[AiEvidenceProjection]:
        return self.values


class FakeSession:
    def __init__(self, evidence: list[AiEvidenceProjection]) -> None:
        self.results: list[Any] = [
            [("passed", 3), ("running", 1)],
            [("failed", 1), ("passed", 7)],
            [("covered", 8), ("gap", 2)],
            [("passed", 2), ("failed", 1)],
            [("critical", 1), ("info", 2)],
            (2, 87.345),
        ]
        self.evidence = evidence

    async def execute(self, _: Any) -> ExecuteResult:
        return ExecuteResult(self.results.pop(0))

    async def scalars(self, _: Any) -> ScalarResult:
        return ScalarResult(self.evidence)


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [False, True])
async def test_operations_counts_current_records_separately_from_activity(empty: bool) -> None:
    session = FakeSession([])
    session.results = (
        [[], [], [], [], (0, 0, 0, 0, 0)]
        if empty
        else [
            [("registered", 2)],
            [("offline", 1), ("online", 3)],
            [("default", 2)],
            [("warning", 4)],
            (2, 1, 12, 3, 8),
        ]
    )
    result = await build_operations(cast(AsyncSession, session), window_hours=24)
    assert result.contract_version == "dashboard-operations-v1"
    assert result.generated_at - result.window_start == timedelta(hours=24)
    assert result.can_networks_total == (0 if empty else 2)
    assert result.can_fd_networks_total == (0 if empty else 1)
    assert result.can_transmissions_total == (0 if empty else 12)
    assert result.can_fault_executions_total == (0 if empty else 3)
    assert result.diagnostic_commands_total == (0 if empty else 8)
    assert sum(item.count for item in result.ecu_states) == (0 if empty else 4)
    assert sum(item.count for item in result.stored_dtc_severities) == (0 if empty else 4)
    assert not session.results


@pytest.mark.asyncio
async def test_overview_calculates_bounded_quality_kpis() -> None:
    now = datetime.now(UTC)
    evidence = AiEvidenceProjection(
        id=uuid4(),
        projection_id="dashboard-evidence-001",
        projection_hash="a" * 64,
        request_id=uuid4(),
        created_by_user_id=uuid4(),
        consumer="dashboard",
        source_type="root_cause_risk",
        source_id="analysis-001",
        subject_type="test_run",
        subject_id="test-run-001",
        status="completed",
        severity="critical",
        headline="Critical thermal risk",
        summary="Recorded evidence indicates a high-priority thermal condition.",
        citations=["artifact://thermal-log"],
        contract_version="ai-evidence-v1",
        created_at=now,
        updated_at=now,
    )
    overview = await build_overview(
        cast(AsyncSession, FakeSession([evidence])), window_hours=24, evidence_limit=10
    )
    assert overview.contract_version == "dashboard-overview-v1"
    assert overview.kpis.test_runs_total == 4
    assert overview.kpis.active_test_runs == 1
    assert overview.kpis.test_case_pass_rate == 87.5
    assert overview.kpis.requirement_coverage_rate == 80.0
    assert overview.kpis.average_mutation_score == 87.34
    assert overview.kpis.dashboard_ai_evidence_total == 3
    assert overview.evidence_cards[0].citations == ["artifact://thermal-log"]


@pytest.mark.asyncio
async def test_overview_uses_none_for_empty_denominators() -> None:
    session = FakeSession([])
    session.results = [[], [], [], [], [], (0, None)]
    overview = await build_overview(cast(AsyncSession, session), window_hours=1, evidence_limit=1)
    assert overview.kpis.test_case_pass_rate is None
    assert overview.kpis.requirement_coverage_rate is None
    assert overview.kpis.average_mutation_score is None


def test_dashboard_permission_is_explicit_and_stable() -> None:
    assert PermissionName.DASHBOARD_READ.value == "dashboard:read"


def test_quality_trends_fill_empty_utc_days_and_calculate_rates() -> None:
    generated_at = datetime(2026, 9, 10, 14, 30, tzinfo=UTC)
    trends = quality_trends_from_rows(
        generated_at=generated_at,
        window_days=3,
        run_rows=[
            (generated_at - timedelta(days=2), "passed", 2),
            (generated_at, "failed", 1),
        ],
        case_rows=[
            (generated_at - timedelta(days=2), "passed", 6),
            (generated_at - timedelta(days=2), "failed", 2),
        ],
    )
    assert trends.contract_version == "dashboard-test-quality-trends-v1"
    assert len(trends.points) == 3
    assert trends.points[0].test_case_pass_rate == 75.0
    assert trends.points[1].test_runs_total == 0
    assert trends.points[1].test_case_pass_rate is None
    assert trends.points[2].test_runs_failed == 1


class FailureResult:
    def __init__(self, rows: list[tuple[CaseResultModel, RunModel]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[CaseResultModel, RunModel]]:
        return self.rows


class FailureSession:
    def __init__(self, rows: list[tuple[CaseResultModel, RunModel]]) -> None:
        self.rows = rows

    async def scalar(self, _: Any) -> int:
        return len(self.rows)

    async def execute(self, _: Any) -> FailureResult:
        return FailureResult(self.rows)


@pytest.mark.asyncio
async def test_failure_drill_down_maps_references_and_truncates_observation() -> None:
    now = datetime.now(UTC)
    run = RunModel(
        id=uuid4(),
        run_id="test-run-failure-001",
        vehicle_id=uuid4(),
        requested_by_user_id=uuid4(),
        name="BMS regression",
        suite="regression",
        metadata_={},
        status="failed",
        progress_percent=100,
        version=2,
        created_at=now,
        updated_at=now,
    )
    result = CaseResultModel(
        id=uuid4(),
        test_run_id=run.id,
        case_id="bms-overheat",
        definition_id="bms-overheat-v1",
        definition_version=1,
        order=1,
        required=True,
        status="failed",
        attempt=1,
        duration_ms=125,
        observed="x" * 600,
        evidence_refs=["artifact://bms-log"],
        version=2,
        created_at=now,
        updated_at=now,
    )
    page = await list_test_failures(
        cast(AsyncSession, FailureSession([(result, run)])),
        window_hours=24,
        suite="regression",
        limit=50,
        offset=0,
    )
    assert page.contract_version == "dashboard-test-failures-v1"
    assert page.total == 1
    assert len(page.items[0].observation or "") == 500
    assert page.items[0].observation_truncated is True
    assert page.items[0].evidence_refs == ["artifact://bms-log"]
