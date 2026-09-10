from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import AiEvidenceProjection
from atep.dashboard.service import build_overview
from atep.identity.permissions import PermissionName


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
