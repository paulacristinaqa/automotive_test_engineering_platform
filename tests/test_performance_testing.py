from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import PerformanceEvidenceContractError
from atep.events.models import OutboxEvent
from atep.performance_testing.models import PerformanceExecution
from atep.performance_testing.schemas import PerformanceExecutionCreate, PerformanceProfileCreate
from atep.performance_testing.service import create_execution, create_profile
from atep.test_runs.models import TestRun as CatalogRun


class Nested(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class FakeSession:
    def __init__(self, existing: Any = None) -> None:
        self.existing = existing
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.existing

    def begin_nested(self) -> Nested:
        return Nested()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()
            if getattr(item, "created_at", None) is None:
                item.created_at = datetime.now(UTC)


def profile_command() -> PerformanceProfileCreate:
    return PerformanceProfileCreate(
        profile_id="api-load-profile-001",
        name="API baseline",
        workload_type="performance",
        target="public-api",
        stages=[{"duration_seconds": 60, "virtual_users": 20, "requests_per_second": 50}],
        thresholds=[
            {"metric": "p95_latency_ms", "operator": "max", "value": 250},
            {"metric": "throughput_rps", "operator": "min", "value": 40},
        ],
        resource_limits={"cpu_cores": 2, "memory_mb": 1024, "gpu_allowed": False},
    )


def execution_command() -> PerformanceExecutionCreate:
    return PerformanceExecutionCreate(
        execution_id="perf-execution-001",
        test_run_id="catalog-run-001",
        sample_count=3000,
        duration_seconds=60,
        metrics={"p95_latency_ms": 210, "throughput_rps": 50},
        evidence_refs=["artifact://k6-summary-001"],
    )


def test_profile_enforces_resource_and_duration_bounds() -> None:
    payload = profile_command().model_dump()
    payload["resource_limits"]["gpu_allowed"] = True
    with pytest.raises(ValidationError, match="GPU"):
        PerformanceProfileCreate(**payload)
    payload = profile_command().model_dump()
    payload["stages"] = [
        {"duration_seconds": 900, "virtual_users": 1, "requests_per_second": 1}
    ] * 5
    with pytest.raises(ValidationError, match="3600"):
        PerformanceProfileCreate(**payload)


@pytest.mark.asyncio
async def test_thresholds_outcome_comparison_and_minimized_evidence() -> None:
    profile_session = FakeSession()
    profile, _ = await create_profile(
        cast(AsyncSession, profile_session),
        command=profile_command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    run = CatalogRun(
        id=uuid4(),
        run_id="catalog-run-001",
        vehicle_id=uuid4(),
        requested_by_user_id=uuid4(),
        name="Performance",
        suite="performance",
        metadata_={},
        status="passed",
        progress_percent=100,
        version=2,
        summary="passed",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = FakeSession()
    execution, duplicate = await create_execution(
        cast(AsyncSession, session),
        profile=profile,
        test_run=run,
        baseline=None,
        command=execution_command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert execution.outcome == "passed"
    assert all(item["passed"] for item in execution.threshold_results)
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.performance.execution.recorded.v1"
    assert "metrics" not in event.payload
    assert (
        next(item for item in session.added if isinstance(item, AuditRecord)).action
        == "performance.execution_recorded"
    )
    baseline = PerformanceExecution(
        id=uuid4(),
        execution_id="perf-baseline-001",
        request_hash="x",
        profile_id=profile.id,
        profile_version=1,
        profile_snapshot={},
        test_run_id=run.id,
        baseline_execution_id=None,
        recorded_by_user_id=uuid4(),
        sample_count=3000,
        duration_seconds=60,
        metrics={"p95_latency_ms": 200, "throughput_rps": 48},
        threshold_results=[],
        comparison=None,
        evidence_refs=[],
        outcome="passed",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    compared = execution_command().model_copy(
        update={
            "execution_id": "perf-execution-002",
            "baseline_execution_id": baseline.execution_id,
            "metrics": {"p95_latency_ms": 280, "throughput_rps": 45},
        }
    )
    failed, _ = await create_execution(
        cast(AsyncSession, FakeSession()),
        profile=profile,
        test_run=run,
        baseline=baseline,
        command=compared,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert failed.outcome == "failed"
    assert failed.comparison is not None
    assert failed.comparison["p95_latency_ms"]["delta"] == 80


@pytest.mark.asyncio
async def test_execution_requires_terminal_run_and_all_threshold_metrics() -> None:
    profile, _ = await create_profile(
        cast(AsyncSession, FakeSession()),
        command=profile_command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    run = CatalogRun(
        id=uuid4(),
        run_id="catalog-run-001",
        vehicle_id=uuid4(),
        requested_by_user_id=uuid4(),
        name="Performance",
        suite="performance",
        metadata_={},
        status="running",
        progress_percent=50,
        version=1,
        summary=None,
        started_at=datetime.now(UTC),
        completed_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    with pytest.raises(PerformanceEvidenceContractError) as error:
        await create_execution(
            cast(AsyncSession, FakeSession()),
            profile=profile,
            test_run=run,
            baseline=None,
            command=execution_command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert "terminal" in str(error.value.details)
    run.status = "passed"
    missing = execution_command().model_copy(update={"metrics": {"p95_latency_ms": 200}})
    with pytest.raises(PerformanceEvidenceContractError) as error:
        await create_execution(
            cast(AsyncSession, FakeSession()),
            profile=profile,
            test_run=run,
            baseline=None,
            command=missing,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert "missing" in str(error.value.details)
