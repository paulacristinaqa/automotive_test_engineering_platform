import hashlib
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from atep.audit.service import record_audit
from atep.core.errors import (
    PerformanceEvidenceConflictError,
    PerformanceEvidenceContractError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event
from atep.performance_testing.models import PerformanceExecution, PerformanceProfile
from atep.performance_testing.schemas import (
    PerformanceExecutionCreate,
    PerformanceExecutionResponse,
    PerformanceProfileCreate,
    PerformanceProfileResponse,
)
from atep.test_runs.models import TestRun


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def profile_response(
    profile: PerformanceProfile, duplicate: bool = False
) -> PerformanceProfileResponse:
    return PerformanceProfileResponse(
        id=profile.id,
        profile_id=profile.profile_id,
        name=profile.name,
        description=profile.description,
        workload_type=profile.workload_type,
        target=profile.target,
        stages=profile.stages,
        thresholds=profile.thresholds,
        resource_limits=profile.resource_limits,
        version=profile.version,
        duplicate=duplicate,
        created_by_user_id=profile.created_by_user_id,
        created_at=profile.created_at,
    )


def execution_response(
    execution: PerformanceExecution,
    profile: PerformanceProfile,
    test_run: TestRun,
    baseline: PerformanceExecution | None,
    duplicate: bool = False,
) -> PerformanceExecutionResponse:
    return PerformanceExecutionResponse(
        id=execution.id,
        execution_id=execution.execution_id,
        profile_id=profile.profile_id,
        profile_version=execution.profile_version,
        test_run_id=test_run.run_id,
        baseline_execution_id=baseline.execution_id if baseline else None,
        sample_count=execution.sample_count,
        duration_seconds=execution.duration_seconds,
        metrics=execution.metrics,
        threshold_results=execution.threshold_results,
        comparison=execution.comparison,
        evidence_refs=execution.evidence_refs,
        outcome=execution.outcome,
        duplicate=duplicate,
        recorded_by_user_id=execution.recorded_by_user_id,
        created_at=execution.created_at,
    )


async def create_profile(
    session: AsyncSession,
    *,
    command: PerformanceProfileCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[PerformanceProfile, bool]:
    payload = command.model_dump(mode="json")
    request_hash = _hash(payload)
    existing = await session.scalar(
        select(PerformanceProfile).where(PerformanceProfile.profile_id == command.profile_id)
    )
    if existing:
        if existing.request_hash == request_hash:
            return existing, True
        raise PerformanceEvidenceConflictError("profile")
    profile = PerformanceProfile(
        profile_id=command.profile_id,
        request_hash=request_hash,
        created_by_user_id=actor_user_id,
        name=command.name,
        description=command.description,
        workload_type=command.workload_type.value,
        target=command.target,
        stages=[item.model_dump(mode="json") for item in command.stages],
        thresholds=[item.model_dump(mode="json") for item in command.thresholds],
        resource_limits=command.resource_limits.model_dump(mode="json"),
        version=1,
    )
    await _persist(session, profile, "profile")
    evidence = {
        "profile_id": profile.profile_id,
        "workload_type": profile.workload_type,
        "stage_count": len(profile.stages),
        "threshold_count": len(profile.thresholds),
        "gpu_allowed": False,
    }
    _record(
        session,
        profile.id,
        "performance_profile",
        "atep.performance.profile.created.v1",
        "performance.profile_created",
        actor_user_id,
        correlation_id,
        evidence,
    )
    return profile, False


async def create_execution(
    session: AsyncSession,
    *,
    profile: PerformanceProfile,
    test_run: TestRun,
    baseline: PerformanceExecution | None,
    command: PerformanceExecutionCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[PerformanceExecution, bool]:
    request_hash = _hash({"profile_id": profile.profile_id, **command.model_dump(mode="json")})
    existing = await session.scalar(
        select(PerformanceExecution).where(
            PerformanceExecution.execution_id == command.execution_id
        )
    )
    if existing:
        if existing.request_hash == request_hash:
            return existing, True
        raise PerformanceEvidenceConflictError("execution")
    if test_run.status not in {"passed", "failed", "cancelled"}:
        raise PerformanceEvidenceContractError("the linked test run must be terminal")
    if command.duration_seconds > sum(item["duration_seconds"] for item in profile.stages):
        raise PerformanceEvidenceContractError("measured duration exceeds the profile stage budget")
    if baseline and baseline.profile_id != profile.id:
        raise PerformanceEvidenceContractError("baseline execution must use the same profile")
    missing = sorted({item["metric"] for item in profile.thresholds} - command.metrics.keys())
    if missing:
        raise PerformanceEvidenceContractError(
            f"threshold metrics are missing: {', '.join(missing)}"
        )
    results = []
    for threshold in profile.thresholds:
        measured = command.metrics[threshold["metric"]]
        passed = (
            measured <= threshold["value"]
            if threshold["operator"] == "max"
            else measured >= threshold["value"]
        )
        results.append({**threshold, "measured": measured, "passed": passed})
    comparison = None
    if baseline:
        shared = sorted(command.metrics.keys() & baseline.metrics.keys())
        comparison = {
            name: {
                "baseline": baseline.metrics[name],
                "current": command.metrics[name],
                "delta": command.metrics[name] - baseline.metrics[name],
            }
            for name in shared
        }
    execution = PerformanceExecution(
        execution_id=command.execution_id,
        request_hash=request_hash,
        profile_id=profile.id,
        profile_version=profile.version,
        profile_snapshot={
            "profile_id": profile.profile_id,
            "workload_type": profile.workload_type,
            "target": profile.target,
            "stages": profile.stages,
            "thresholds": profile.thresholds,
            "resource_limits": profile.resource_limits,
        },
        test_run_id=test_run.id,
        baseline_execution_id=baseline.id if baseline else None,
        recorded_by_user_id=actor_user_id,
        sample_count=command.sample_count,
        duration_seconds=command.duration_seconds,
        metrics=command.metrics,
        threshold_results=results,
        comparison=comparison,
        evidence_refs=command.evidence_refs,
        outcome="passed" if all(item["passed"] for item in results) else "failed",
    )
    await _persist(session, execution, "execution")
    evidence = {
        "execution_id": execution.execution_id,
        "profile_id": profile.profile_id,
        "test_run_id": test_run.run_id,
        "outcome": execution.outcome,
        "sample_count": execution.sample_count,
        "threshold_count": len(results),
        "failed_threshold_count": sum(not item["passed"] for item in results),
        "has_baseline": baseline is not None,
    }
    _record(
        session,
        execution.id,
        "performance_execution",
        "atep.performance.execution.recorded.v1",
        "performance.execution_recorded",
        actor_user_id,
        correlation_id,
        evidence,
    )
    return execution, False


async def _persist(session: AsyncSession, resource: object, kind: str) -> None:
    try:
        async with session.begin_nested():
            session.add(resource)
            await session.flush()
    except IntegrityError as exc:
        raise PerformanceEvidenceConflictError(kind) from exc


def _record(
    session: AsyncSession,
    resource_id: UUID,
    resource_type: str,
    event_type: str,
    action: str,
    actor: UUID,
    correlation_id: UUID | None,
    payload: dict[str, object],
) -> None:
    enqueue_event(
        session,
        event_type=event_type,
        aggregate_type=resource_type,
        aggregate_id=resource_id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=payload,
        correlation_id=correlation_id,
    )


async def require_profile(session: AsyncSession, profile_id: str) -> PerformanceProfile:
    profile = await session.scalar(
        select(PerformanceProfile).where(PerformanceProfile.profile_id == profile_id)
    )
    if not profile:
        raise ResourceNotFoundError("performance_profile")
    return profile


async def require_execution(session: AsyncSession, execution_id: str) -> PerformanceExecution:
    execution = await session.scalar(
        select(PerformanceExecution).where(PerformanceExecution.execution_id == execution_id)
    )
    if not execution:
        raise ResourceNotFoundError("performance_execution")
    return execution


async def list_profiles(
    session: AsyncSession, limit: int, offset: int
) -> tuple[list[PerformanceProfile], int]:
    query = select(PerformanceProfile)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(PerformanceProfile.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows), int(total or 0)


async def list_executions(
    session: AsyncSession, profile: PerformanceProfile, limit: int, offset: int
) -> tuple[list[tuple[PerformanceExecution, TestRun, PerformanceExecution | None]], int]:
    baseline = aliased(PerformanceExecution)
    query = (
        select(PerformanceExecution, TestRun, baseline)
        .join(TestRun, PerformanceExecution.test_run_id == TestRun.id)
        .outerjoin(baseline, PerformanceExecution.baseline_execution_id == baseline.id)
        .where(PerformanceExecution.profile_id == profile.id)
    )
    total = await session.scalar(
        select(func.count()).select_from(
            select(PerformanceExecution)
            .where(PerformanceExecution.profile_id == profile.id)
            .subquery()
        )
    )
    result = await session.execute(
        query.order_by(PerformanceExecution.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.tuples()), int(total or 0)
