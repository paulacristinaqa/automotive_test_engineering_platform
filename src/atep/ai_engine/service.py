import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.adapters import ADAPTERS, AnalysisAdapter
from atep.ai_engine.models import AiAnalysisExecution, AiAnalysisRequest
from atep.ai_engine.schemas import (
    AiAnalysisExecute,
    AiAnalysisExecutionResponse,
    AiAnalysisRequestCreate,
    AiAnalysisRequestResponse,
    AiAnalysisResult,
    AiTask,
)
from atep.audit.service import record_audit
from atep.core.errors import (
    AiAnalysisConflictError,
    AiAnalysisExecutionConflictError,
    AiAnalysisExecutionError,
    AiAnalysisPolicyError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event


def _request_hash(command: AiAnalysisRequestCreate) -> str:
    payload = json.dumps(command.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def request_response(
    request: AiAnalysisRequest, *, duplicate: bool = False
) -> AiAnalysisRequestResponse:
    return AiAnalysisRequestResponse(
        id=request.id,
        request_id=request.request_id,
        task=request.task,
        subject_type=request.subject_type,
        subject_id=request.subject_id,
        provider_policy=request.provider_policy,
        data_classification=request.data_classification,
        evidence_refs=request.evidence_refs,
        context=request.context,
        instructions=request.instructions,
        status=request.status,
        attempt_count=request.attempt_count,
        duplicate=duplicate,
        requested_by_user_id=request.requested_by_user_id,
        created_at=request.created_at,
    )


async def create_request(
    session: AsyncSession,
    *,
    command: AiAnalysisRequestCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AiAnalysisRequest, bool]:
    request_hash = _request_hash(command)
    existing = await session.scalar(
        select(AiAnalysisRequest).where(AiAnalysisRequest.request_id == command.request_id)
    )
    if existing is not None:
        if existing.request_hash == request_hash:
            return existing, True
        raise AiAnalysisConflictError()
    if command.data_classification == "restricted" and command.provider_policy != "local_only":
        raise AiAnalysisPolicyError("restricted data requires the local_only provider policy")

    request = AiAnalysisRequest(
        request_id=command.request_id,
        request_hash=request_hash,
        requested_by_user_id=actor_user_id,
        task=command.task.value,
        subject_type=command.subject_type.value,
        subject_id=command.subject_id,
        provider_policy=command.provider_policy.value,
        data_classification=command.data_classification.value,
        evidence_refs=command.evidence_refs,
        context=command.context,
        instructions=command.instructions,
        status="queued",
        attempt_count=0,
    )
    try:
        async with session.begin_nested():
            session.add(request)
            await session.flush()
    except IntegrityError as exc:
        raise AiAnalysisConflictError() from exc
    evidence = {
        "request_id": request.request_id,
        "task": request.task,
        "subject_type": request.subject_type,
        "subject_id": request.subject_id,
        "provider_policy": request.provider_policy,
        "data_classification": request.data_classification,
        "evidence_ref_count": len(request.evidence_refs),
    }
    enqueue_event(
        session,
        event_type="atep.ai.analysis.requested.v1",
        aggregate_type="ai_analysis_request",
        aggregate_id=request.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ai_analysis.requested",
        resource_type="ai_analysis_request",
        resource_id=request.id,
        details=evidence,
        correlation_id=correlation_id,
    )
    return request, False


def execution_response(
    execution: AiAnalysisExecution,
    *,
    request: AiAnalysisRequest,
    duplicate: bool = False,
) -> AiAnalysisExecutionResponse:
    return AiAnalysisExecutionResponse(
        id=execution.id,
        execution_id=execution.execution_id,
        request_id=request.request_id,
        attempt=execution.attempt,
        provider_id=execution.provider_id,
        provider_kind=execution.provider_kind,
        status=execution.status,
        rule_version=execution.rule_version,
        result=AiAnalysisResult.model_validate(execution.result),
        error_code=execution.error_code,
        duplicate=duplicate,
        executed_by_user_id=execution.executed_by_user_id,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
    )


def _execution_hash(request: AiAnalysisRequest, command: AiAnalysisExecute) -> str:
    value = {"request_id": request.request_id, **command.model_dump(mode="json")}
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


async def execute_request(
    session: AsyncSession,
    *,
    request: AiAnalysisRequest,
    command: AiAnalysisExecute,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    adapters: Mapping[str, AnalysisAdapter] = ADAPTERS,
) -> tuple[AiAnalysisExecution, bool]:
    execution_hash = _execution_hash(request, command)
    existing = await session.scalar(
        select(AiAnalysisExecution).where(AiAnalysisExecution.execution_id == command.execution_id)
    )
    if existing is not None:
        if existing.execution_hash == execution_hash:
            return existing, True
        raise AiAnalysisExecutionConflictError()
    if request.status == "succeeded":
        raise AiAnalysisExecutionError("a succeeded request cannot be executed again")
    if request.status == "running":
        raise AiAnalysisExecutionError("the request is already running")
    if request.attempt_count >= 3:
        raise AiAnalysisExecutionError("the request has reached the three-attempt limit")
    adapter = adapters.get(command.provider_id)
    if adapter is None:
        raise AiAnalysisPolicyError("the requested provider adapter is disabled")
    if adapter.provider_kind == "external":
        if request.provider_policy != "external_allowed":
            raise AiAnalysisPolicyError("external adapters require external_allowed policy")
        if request.data_classification == "restricted":
            raise AiAnalysisPolicyError("restricted data cannot be sent to an external adapter")

    started_at = datetime.now(UTC)
    request.status = "running"
    request.attempt_count += 1
    status = "succeeded"
    error_code = None
    try:
        result = adapter.analyze(
            task=request.task,
            context=request.context,
            evidence_refs=request.evidence_refs,
        )
    except Exception:
        status = "failed"
        error_code = "adapter_failure"
        result = AiAnalysisResult(
            summary="The analysis adapter failed without producing advisory output.",
            findings=[],
            recommendations=[
                "Review worker diagnostics and retry only after correcting the cause."
            ],
            confidence=0,
        )
    completed_at = datetime.now(UTC)
    request.status = status
    execution = AiAnalysisExecution(
        execution_id=command.execution_id,
        execution_hash=execution_hash,
        request_id=request.id,
        executed_by_user_id=actor_user_id,
        attempt=request.attempt_count,
        provider_id=adapter.provider_id,
        provider_kind=adapter.provider_kind,
        status=status,
        rule_version=adapter.version,
        result=result.model_dump(mode="json"),
        error_code=error_code,
        started_at=started_at,
        completed_at=completed_at,
    )
    try:
        async with session.begin_nested():
            session.add(execution)
            await session.flush()
    except IntegrityError as exc:
        raise AiAnalysisExecutionConflictError() from exc
    evidence = {
        "execution_id": execution.execution_id,
        "request_id": request.request_id,
        "attempt": execution.attempt,
        "provider_id": execution.provider_id,
        "provider_kind": execution.provider_kind,
        "status": execution.status,
        "rule_version": execution.rule_version,
        "finding_count": len(result.findings),
        "recommendation_count": len(result.recommendations),
        "error_code": execution.error_code,
    }
    enqueue_event(
        session,
        event_type="atep.ai.analysis.completed.v1",
        aggregate_type="ai_analysis_execution",
        aggregate_id=execution.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ai_analysis.completed",
        resource_type="ai_analysis_execution",
        resource_id=execution.id,
        details=evidence,
        correlation_id=correlation_id,
    )
    return execution, False


async def list_executions(
    session: AsyncSession,
    *,
    request: AiAnalysisRequest,
    limit: int,
    offset: int,
) -> tuple[list[AiAnalysisExecution], int]:
    base = select(AiAnalysisExecution).where(AiAnalysisExecution.request_id == request.id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(AiAnalysisExecution.attempt.desc()).limit(limit).offset(offset)
    )
    return list(rows), int(total or 0)


async def list_requests(
    session: AsyncSession, *, limit: int, offset: int, task: AiTask | None
) -> tuple[list[AiAnalysisRequest], int]:
    query = select(AiAnalysisRequest)
    if task is not None:
        query = query.where(AiAnalysisRequest.task == task.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(AiAnalysisRequest.created_at.desc(), AiAnalysisRequest.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


async def require_request(
    session: AsyncSession, request_id: str, *, for_update: bool = False
) -> AiAnalysisRequest:
    query = select(AiAnalysisRequest).where(AiAnalysisRequest.request_id == request_id)
    if for_update:
        query = query.with_for_update()
    request = await session.scalar(query)
    if request is None:
        raise ResourceNotFoundError("ai_analysis_request")
    return request
