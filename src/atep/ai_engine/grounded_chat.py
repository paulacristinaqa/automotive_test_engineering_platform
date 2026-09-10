import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.log_intelligence import _sanitize
from atep.ai_engine.models import AiAnalysisRequest, AiChatConversation, AiChatExchange
from atep.ai_engine.schemas import (
    AiChatConversationCreate,
    AiChatConversationResponse,
    AiChatExchangeCreate,
    AiChatExchangeResponse,
    AiChatPurgeResponse,
)
from atep.audit.service import record_audit
from atep.core.errors import AiChatConflictError, AiChatContractError, ResourceNotFoundError
from atep.events.outbox import enqueue_event

RULE_VERSION = "grounded-chat-rules-v1"
MAX_EXCHANGES = 50


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def conversation_response(
    conversation: AiChatConversation,
    *,
    request: AiAnalysisRequest,
    duplicate: bool = False,
) -> AiChatConversationResponse:
    return AiChatConversationResponse(
        id=conversation.id,
        conversation_id=conversation.conversation_id,
        request_id=request.request_id,
        title=conversation.title,
        retention_days=conversation.retention_days,
        expires_at=conversation.expires_at,
        status=conversation.status,
        message_count=conversation.message_count,
        owner_user_id=conversation.owner_user_id,
        purged_at=conversation.purged_at,
        duplicate=duplicate,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def exchange_response(
    exchange: AiChatExchange, *, duplicate: bool = False
) -> AiChatExchangeResponse:
    return AiChatExchangeResponse(
        id=exchange.id,
        exchange_id=exchange.exchange_id,
        sequence=exchange.sequence,
        question=exchange.question,
        answer=exchange.answer,
        citations=exchange.citations,
        rule_version=exchange.rule_version,
        limitations=exchange.limitations,
        duplicate=duplicate,
        created_by_user_id=exchange.created_by_user_id,
        created_at=exchange.created_at,
    )


async def create_conversation(
    session: AsyncSession,
    *,
    request: AiAnalysisRequest,
    command: AiChatConversationCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AiChatConversation, bool]:
    creation_hash = _hash({"request_id": request.request_id, **command.model_dump(mode="json")})
    existing = await session.scalar(
        select(AiChatConversation).where(
            AiChatConversation.conversation_id == command.conversation_id
        )
    )
    if existing is not None:
        if existing.owner_user_id == actor_user_id and existing.creation_hash == creation_hash:
            return existing, True
        raise AiChatConflictError()
    if request.requested_by_user_id != actor_user_id:
        raise AiChatContractError("only the analysis request owner may create its conversation")
    now = datetime.now(UTC)
    conversation = AiChatConversation(
        conversation_id=command.conversation_id,
        creation_hash=creation_hash,
        request_id=request.id,
        owner_user_id=actor_user_id,
        title=command.title.strip(),
        retention_days=command.retention_days,
        expires_at=now + timedelta(days=command.retention_days),
        status="active",
        message_count=0,
    )
    try:
        async with session.begin_nested():
            session.add(conversation)
            await session.flush()
    except IntegrityError as exc:
        raise AiChatConflictError() from exc
    _record(session, conversation, request, actor_user_id, correlation_id, "created")
    return conversation, False


def _answer(request: AiAnalysisRequest, question: str, citations: list[str]) -> str:
    lowered = question.lower()
    prefix = (
        f"For {request.subject_type} {request.subject_id}, the governed request classifies this "
        f"as {request.task}."
    )
    if "risk" in lowered:
        guidance = (
            "Use the cited evidence to review likelihood, impact, and detectability before "
            "prioritizing risk."
        )
    elif "root" in lowered or "cause" in lowered:
        guidance = (
            "Use the cited evidence to investigate candidate contributors; association does "
            "not prove causality."
        )
    elif "test" in lowered or "coverage" in lowered:
        guidance = (
            "Compare the cited evidence with approved requirements before proposing or "
            "executing any test."
        )
    elif "log" in lowered or "failure" in lowered or "error" in lowered:
        guidance = (
            "Review the cited evidence for observable failure signals and preserve the original "
            "timeline."
        )
    else:
        guidance = (
            "Review the cited evidence within the governed request before drawing a conclusion."
        )
    return (
        f"{prefix} {guidance} This local response cites {len(citations)} governed reference(s) "
        "and has no authority to change vehicle, test, catalog, or schedule state."
    )


async def create_exchange(
    session: AsyncSession,
    *,
    conversation: AiChatConversation,
    request: AiAnalysisRequest,
    command: AiChatExchangeCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AiChatExchange, bool]:
    exchange_hash = _hash(
        {"conversation_id": conversation.conversation_id, **command.model_dump(mode="json")}
    )
    existing = await session.scalar(
        select(AiChatExchange).where(AiChatExchange.exchange_id == command.exchange_id)
    )
    if existing is not None:
        if existing.created_by_user_id == actor_user_id and existing.exchange_hash == exchange_hash:
            return existing, True
        raise AiChatConflictError()
    if conversation.owner_user_id != actor_user_id:
        raise ResourceNotFoundError("ai_chat_conversation")
    if conversation.status != "active" or conversation.expires_at <= datetime.now(UTC):
        raise AiChatContractError("the conversation is expired")
    if conversation.message_count >= MAX_EXCHANGES:
        raise AiChatContractError("the conversation has reached the 50-exchange limit")
    if not set(command.evidence_refs) <= set(request.evidence_refs):
        raise AiChatContractError("every citation must be governed by the analysis request")
    sanitized_question = _sanitize(command.question.strip())
    exchange = AiChatExchange(
        exchange_id=command.exchange_id,
        exchange_hash=exchange_hash,
        conversation_id=conversation.id,
        created_by_user_id=actor_user_id,
        sequence=conversation.message_count + 1,
        question=sanitized_question,
        answer=_answer(request, sanitized_question, command.evidence_refs),
        citations=command.evidence_refs,
        rule_version=RULE_VERSION,
        limitations=[
            "Citations identify governed references but do not verify their content.",
            "The response is advisory and does not prove causality.",
            "The response cannot mutate vehicle or test state.",
        ],
    )
    try:
        async with session.begin_nested():
            session.add(exchange)
            conversation.message_count += 1
            await session.flush()
    except IntegrityError as exc:
        raise AiChatConflictError() from exc
    _record(session, conversation, request, actor_user_id, correlation_id, "answered")
    return exchange, False


async def require_conversation(
    session: AsyncSession,
    conversation_id: str,
    *,
    actor_user_id: UUID,
    for_update: bool = False,
) -> tuple[AiChatConversation, AiAnalysisRequest]:
    query = (
        select(AiChatConversation, AiAnalysisRequest)
        .join(AiAnalysisRequest, AiAnalysisRequest.id == AiChatConversation.request_id)
        .where(
            AiChatConversation.conversation_id == conversation_id,
            AiChatConversation.owner_user_id == actor_user_id,
        )
    )
    if for_update:
        query = query.with_for_update()
    row = (await session.execute(query)).one_or_none()
    if row is None:
        raise ResourceNotFoundError("ai_chat_conversation")
    return row[0], row[1]


async def list_conversations(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    limit: int,
    offset: int,
    status: str | None,
) -> tuple[list[tuple[AiChatConversation, AiAnalysisRequest]], int]:
    filters = [AiChatConversation.owner_user_id == actor_user_id]
    if status is not None:
        filters.append(AiChatConversation.status == status)
    total = await session.scalar(select(func.count(AiChatConversation.id)).where(*filters))
    rows = await session.execute(
        select(AiChatConversation, AiAnalysisRequest)
        .join(AiAnalysisRequest, AiAnalysisRequest.id == AiChatConversation.request_id)
        .where(*filters)
        .order_by(AiChatConversation.created_at.desc(), AiChatConversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.tuples()), int(total or 0)


async def list_exchanges(
    session: AsyncSession,
    *,
    conversation: AiChatConversation,
    limit: int,
    offset: int,
) -> tuple[list[AiChatExchange], int]:
    base = select(AiChatExchange).where(AiChatExchange.conversation_id == conversation.id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(base.order_by(AiChatExchange.sequence).limit(limit).offset(offset))
    return list(rows), int(total or 0)


async def purge_expired(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> AiChatPurgeResponse:
    now = datetime.now(UTC)
    conversations = list(
        await session.scalars(
            select(AiChatConversation)
            .where(AiChatConversation.status == "active", AiChatConversation.expires_at <= now)
            .with_for_update()
        )
    )
    exchange_count = 0
    for conversation in conversations:
        exchange_count += int(
            await session.scalar(
                select(func.count(AiChatExchange.id)).where(
                    AiChatExchange.conversation_id == conversation.id
                )
            )
            or 0
        )
        await session.execute(
            delete(AiChatExchange).where(AiChatExchange.conversation_id == conversation.id)
        )
        conversation.status = "expired"
        conversation.message_count = 0
        conversation.purged_at = now
        evidence = {"conversation_id": conversation.conversation_id, "status": "expired"}
        enqueue_event(
            session,
            event_type="atep.ai.chat.expired.v1",
            aggregate_type="ai_chat_conversation",
            aggregate_id=conversation.id,
            payload=evidence,
            correlation_id=correlation_id,
        )
        record_audit(
            session,
            actor_user_id=actor_user_id,
            action="ai_chat.expired",
            resource_type="ai_chat_conversation",
            resource_id=conversation.id,
            details=evidence,
            correlation_id=correlation_id,
        )
    await session.flush()
    return AiChatPurgeResponse(
        purged_conversation_count=len(conversations), purged_exchange_count=exchange_count
    )


def _record(
    session: AsyncSession,
    conversation: AiChatConversation,
    request: AiAnalysisRequest,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    action: str,
) -> None:
    evidence = {
        "conversation_id": conversation.conversation_id,
        "request_id": request.request_id,
        "status": action,
        "message_count": conversation.message_count,
        "retention_days": conversation.retention_days,
    }
    enqueue_event(
        session,
        event_type=f"atep.ai.chat.{action}.v1",
        aggregate_type="ai_chat_conversation",
        aggregate_id=conversation.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action=f"ai_chat.{action}",
        resource_type="ai_chat_conversation",
        resource_id=conversation.id,
        details=evidence,
        correlation_id=correlation_id,
    )
