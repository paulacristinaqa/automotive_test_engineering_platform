import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import (
    AiAnalysisExecution,
    AiAnalysisRequest,
    AiChatConversation,
    AiChatExchange,
    AiEvidenceProjection,
    AiLogAnalysis,
    AiRootCauseRiskAnalysis,
    AiTestSuggestion,
)
from atep.ai_engine.schemas import AiEvidenceProjectionCreate, AiEvidenceProjectionResponse
from atep.audit.service import record_audit
from atep.core.errors import (
    AiEvidenceProjectionConflictError,
    AiEvidenceProjectionContractError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event

CONTRACT_VERSION = "ai-evidence-v1"
SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _hash(payload: dict[str, Any]) -> str:
    value = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(value).hexdigest()


def _bounded(value: object, maximum: int) -> str:
    return " ".join(str(value).split())[:maximum]


def _unique_refs(values: list[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        ref = str(value)
        if ref and ref not in result:
            result.append(ref)
    return result[:20]


async def _source(
    session: AsyncSession,
    command: AiEvidenceProjectionCreate,
    actor_user_id: UUID,
) -> tuple[AiAnalysisRequest, dict[str, Any]]:
    if command.source_type == "analysis_execution":
        execution_row = (
            await session.execute(
                select(AiAnalysisExecution, AiAnalysisRequest)
                .join(AiAnalysisRequest, AiAnalysisRequest.id == AiAnalysisExecution.request_id)
                .where(AiAnalysisExecution.execution_id == command.source_id)
            )
        ).one_or_none()
        if execution_row is not None:
            execution, request = execution_row
            result = execution.result
            citations = _unique_refs(
                [
                    ref
                    for finding in result.get("findings", [])
                    for ref in finding.get("evidence_refs", [])
                ]
            )
            return request, {
                "status": execution.status,
                "severity": "high" if execution.status == "failed" else "info",
                "headline": f"AI analysis {execution.status}",
                "summary": result.get("summary", "No advisory summary was produced."),
                "citations": citations,
            }
    elif command.source_type == "log_analysis":
        log_row = (
            await session.execute(
                select(AiLogAnalysis, AiAnalysisRequest)
                .join(AiAnalysisRequest, AiAnalysisRequest.id == AiLogAnalysis.request_id)
                .where(AiLogAnalysis.analysis_id == command.source_id)
            )
        ).one_or_none()
        if log_row is not None:
            analysis, request = log_row
            severities = [str(item.get("severity", "info")) for item in analysis.anomalies]
            severity = max(severities, key=lambda item: SEVERITY_ORDER.get(item, 0), default="info")
            return request, {
                "status": "completed",
                "severity": severity,
                "headline": f"Log analysis found {len(analysis.anomalies)} anomaly signal(s)",
                "summary": analysis.explanation.get("summary", "Review the cited log evidence."),
                "citations": request.evidence_refs,
            }
    elif command.source_type == "test_suggestion":
        suggestion_row = (
            await session.execute(
                select(AiTestSuggestion, AiAnalysisRequest)
                .join(AiAnalysisRequest, AiAnalysisRequest.id == AiTestSuggestion.request_id)
                .where(AiTestSuggestion.suggestion_id == command.source_id)
            )
        ).one_or_none()
        if suggestion_row is not None:
            suggestion, request = suggestion_row
            return request, {
                "status": suggestion.status,
                "severity": "low" if suggestion.status == "rejected" else "info",
                "headline": f"Test suggestion {suggestion.status}",
                "summary": suggestion.rationale,
                "citations": suggestion.evidence_refs,
            }
    elif command.source_type == "root_cause_risk":
        risk_row = (
            await session.execute(
                select(AiRootCauseRiskAnalysis, AiAnalysisRequest)
                .join(AiAnalysisRequest, AiAnalysisRequest.id == AiRootCauseRiskAnalysis.request_id)
                .where(AiRootCauseRiskAnalysis.analysis_id == command.source_id)
            )
        ).one_or_none()
        if risk_row is not None:
            analysis, request = risk_row
            top = analysis.hypotheses[0] if analysis.hypotheses else None
            summary = (
                str(top["statement"])
                if top is not None
                else "No evidence-ranked hypothesis was produced."
            )
            citations = _unique_refs(list(top.get("evidence_refs", [])) if top else [])
            return request, {
                "status": "evaluated" if analysis.evaluation_id else "completed",
                "severity": analysis.risk_band,
                "headline": f"{analysis.risk_band.title()} risk score {analysis.risk_score}",
                "summary": summary,
                "citations": citations,
            }
    elif command.source_type == "chat_exchange":
        chat_row = (
            await session.execute(
                select(AiChatExchange, AiChatConversation, AiAnalysisRequest)
                .join(AiChatConversation, AiChatConversation.id == AiChatExchange.conversation_id)
                .join(AiAnalysisRequest, AiAnalysisRequest.id == AiChatConversation.request_id)
                .where(AiChatExchange.exchange_id == command.source_id)
            )
        ).one_or_none()
        if chat_row is not None:
            exchange, conversation, request = chat_row
            if conversation.owner_user_id != actor_user_id:
                raise ResourceNotFoundError("ai_evidence_source")
            return request, {
                "status": "answered",
                "severity": "info",
                "headline": "Grounded advisory answer",
                "summary": exchange.answer,
                "citations": exchange.citations,
            }
    raise ResourceNotFoundError("ai_evidence_source")


def projection_response(
    projection: AiEvidenceProjection,
    *,
    request: AiAnalysisRequest,
    duplicate: bool = False,
) -> AiEvidenceProjectionResponse:
    return AiEvidenceProjectionResponse(
        id=projection.id,
        projection_id=projection.projection_id,
        request_id=request.request_id,
        consumer=projection.consumer,
        source_type=projection.source_type,
        source_id=projection.source_id,
        subject_type=projection.subject_type,
        subject_id=projection.subject_id,
        status=projection.status,
        severity=projection.severity,
        headline=projection.headline,
        summary=projection.summary,
        citations=projection.citations,
        contract_version=projection.contract_version,
        duplicate=duplicate,
        created_by_user_id=projection.created_by_user_id,
        created_at=projection.created_at,
    )


async def create_projection(
    session: AsyncSession,
    *,
    command: AiEvidenceProjectionCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AiEvidenceProjection, AiAnalysisRequest, bool]:
    request, data = await _source(session, command, actor_user_id)
    if not data["citations"]:
        raise AiEvidenceProjectionContractError("the source has no governed citations")
    payload = {**command.model_dump(mode="json"), **data, "contract_version": CONTRACT_VERSION}
    projection_hash = _hash(payload)
    existing = await session.scalar(
        select(AiEvidenceProjection).where(
            AiEvidenceProjection.projection_id == command.projection_id
        )
    )
    if existing is not None:
        if existing.projection_hash == projection_hash:
            return existing, request, True
        raise AiEvidenceProjectionConflictError()
    projection = AiEvidenceProjection(
        projection_id=command.projection_id,
        projection_hash=projection_hash,
        request_id=request.id,
        created_by_user_id=actor_user_id,
        consumer=command.consumer,
        source_type=command.source_type,
        source_id=command.source_id,
        subject_type=request.subject_type,
        subject_id=request.subject_id,
        status=_bounded(data["status"], 24),
        severity=data["severity"],
        headline=_bounded(data["headline"], 160),
        summary=_bounded(data["summary"], 1000),
        citations=_unique_refs(data["citations"]),
        contract_version=CONTRACT_VERSION,
    )
    try:
        async with session.begin_nested():
            session.add(projection)
            await session.flush()
    except IntegrityError as exc:
        raise AiEvidenceProjectionConflictError() from exc
    evidence = {
        "projection_id": projection.projection_id,
        "consumer": projection.consumer,
        "source_type": projection.source_type,
        "source_id": projection.source_id,
        "subject_type": projection.subject_type,
        "subject_id": projection.subject_id,
        "status": projection.status,
        "severity": projection.severity,
        "citation_count": len(projection.citations),
        "contract_version": projection.contract_version,
    }
    enqueue_event(
        session,
        event_type="atep.ai.evidence_projection.created.v1",
        aggregate_type="ai_evidence_projection",
        aggregate_id=projection.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ai_evidence_projection.created",
        resource_type="ai_evidence_projection",
        resource_id=projection.id,
        details=evidence,
        correlation_id=correlation_id,
    )
    return projection, request, False


async def require_projection(
    session: AsyncSession, projection_id: str
) -> tuple[AiEvidenceProjection, AiAnalysisRequest]:
    row = (
        await session.execute(
            select(AiEvidenceProjection, AiAnalysisRequest)
            .join(AiAnalysisRequest, AiAnalysisRequest.id == AiEvidenceProjection.request_id)
            .where(AiEvidenceProjection.projection_id == projection_id)
        )
    ).one_or_none()
    if row is None:
        raise ResourceNotFoundError("ai_evidence_projection")
    return row[0], row[1]


async def list_projections(
    session: AsyncSession,
    *,
    consumer: str,
    subject_type: str | None,
    subject_id: str | None,
    severity: str | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[AiEvidenceProjection, AiAnalysisRequest]], int]:
    filters = [AiEvidenceProjection.consumer == consumer]
    if subject_type is not None:
        filters.append(AiEvidenceProjection.subject_type == subject_type)
    if subject_id is not None:
        filters.append(AiEvidenceProjection.subject_id == subject_id)
    if severity is not None:
        filters.append(AiEvidenceProjection.severity == severity)
    total = await session.scalar(select(func.count(AiEvidenceProjection.id)).where(*filters))
    rows = await session.execute(
        select(AiEvidenceProjection, AiAnalysisRequest)
        .join(AiAnalysisRequest, AiAnalysisRequest.id == AiEvidenceProjection.request_id)
        .where(*filters)
        .order_by(AiEvidenceProjection.created_at.desc(), AiEvidenceProjection.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.tuples()), int(total or 0)
