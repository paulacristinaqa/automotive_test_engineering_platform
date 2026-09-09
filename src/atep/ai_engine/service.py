import hashlib
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import AiAnalysisRequest
from atep.ai_engine.schemas import AiAnalysisRequestCreate, AiAnalysisRequestResponse, AiTask
from atep.audit.service import record_audit
from atep.core.errors import AiAnalysisConflictError, AiAnalysisPolicyError, ResourceNotFoundError
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


async def require_request(session: AsyncSession, request_id: str) -> AiAnalysisRequest:
    request = await session.scalar(
        select(AiAnalysisRequest).where(AiAnalysisRequest.request_id == request_id)
    )
    if request is None:
        raise ResourceNotFoundError("ai_analysis_request")
    return request
