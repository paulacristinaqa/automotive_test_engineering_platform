from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.grounded_chat import create_conversation, create_exchange, purge_expired
from atep.ai_engine.models import AiAnalysisRequest, AiChatConversation, AiChatExchange
from atep.ai_engine.schemas import AiChatConversationCreate, AiChatExchangeCreate
from atep.audit.models import AuditRecord
from atep.core.errors import AiChatConflictError, AiChatContractError, ResourceNotFoundError
from atep.events.models import OutboxEvent


class NestedTransaction(AbstractAsyncContextManager[None]):
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
    def __init__(
        self,
        scalar_results: list[object | None] | None = None,
        scalars_results: list[list[Any]] | None = None,
    ) -> None:
        self.scalar_results = list(scalar_results or [])
        self.scalars_results = list(scalars_results or [])
        self.added: list[Any] = []
        self.executed: list[Any] = []

    async def scalar(self, _: Any) -> object | None:
        return self.scalar_results.pop(0) if self.scalar_results else None

    async def scalars(self, _: Any) -> list[Any]:
        return self.scalars_results.pop(0) if self.scalars_results else []

    async def execute(self, statement: Any) -> None:
        self.executed.append(statement)

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        now = datetime.now(UTC)
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()
            if getattr(value, "created_at", None) is None:
                value.created_at = now
            value.updated_at = now


def analysis_request(owner: UUID) -> AiAnalysisRequest:
    return AiAnalysisRequest(
        id=uuid4(),
        request_id="ai-chat-request-001",
        request_hash="a" * 64,
        requested_by_user_id=owner,
        task="failure_explanation",
        subject_type="test_run",
        subject_id="test-run-001",
        provider_policy="local_only",
        data_classification="internal",
        evidence_refs=["log-analysis://bms-001", "diagnostic://dtc-p0a80"],
        context={},
        instructions="Answer only from governed evidence.",
        status="queued",
        attempt_count=0,
    )


def conversation(owner: UUID, *, count: int = 0) -> AiChatConversation:
    now = datetime.now(UTC)
    return AiChatConversation(
        id=uuid4(),
        conversation_id="grounded-chat-001",
        creation_hash="b" * 64,
        request_id=uuid4(),
        owner_user_id=owner,
        title="Battery failure review",
        retention_days=7,
        expires_at=now + timedelta(days=7),
        status="active",
        message_count=count,
        created_at=now,
        updated_at=now,
    )


def test_chat_contract_bounds_retention_and_unique_citations() -> None:
    with pytest.raises(ValidationError):
        AiChatConversationCreate(
            conversation_id="grounded-chat-001", title="Review", retention_days=31
        )
    with pytest.raises(ValidationError, match="evidence references must be unique"):
        AiChatExchangeCreate(
            exchange_id="grounded-exchange-001",
            question="What failed?",
            evidence_refs=["artifact://one", "artifact://one"],
        )


@pytest.mark.asyncio
async def test_conversation_is_owner_bound_idempotent_and_minimized() -> None:
    owner = uuid4()
    request = analysis_request(owner)
    command = AiChatConversationCreate(
        conversation_id="grounded-chat-001", title="Battery failure review", retention_days=7
    )
    session = FakeSession()
    created, duplicate = await create_conversation(
        cast(AsyncSession, session),
        request=request,
        command=command,
        actor_user_id=owner,
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert created.expires_at > datetime.now(UTC) + timedelta(days=6)
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.ai.chat.created.v1"
    assert "title" not in event.payload and "question" not in event.payload
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert audit.action == "ai_chat.created"

    replay, duplicate = await create_conversation(
        cast(AsyncSession, FakeSession([created])),
        request=request,
        command=command,
        actor_user_id=owner,
        correlation_id=None,
    )
    assert replay is created and duplicate is True
    with pytest.raises(AiChatConflictError):
        await create_conversation(
            cast(AsyncSession, FakeSession([created])),
            request=request,
            command=command.model_copy(update={"retention_days": 14}),
            actor_user_id=owner,
            correlation_id=None,
        )
    with pytest.raises(AiChatContractError, match="governed contract"):
        await create_conversation(
            cast(AsyncSession, FakeSession()),
            request=request,
            command=command,
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_exchange_is_grounded_sanitized_advisory_and_idempotent() -> None:
    owner = uuid4()
    request = analysis_request(owner)
    chat = conversation(owner)
    command = AiChatExchangeCreate(
        exchange_id="grounded-exchange-001",
        question="What is the root cause? token=secret-value person@example.com",
        evidence_refs=["log-analysis://bms-001"],
    )
    session = FakeSession()
    exchange, duplicate = await create_exchange(
        cast(AsyncSession, session),
        conversation=chat,
        request=request,
        command=command,
        actor_user_id=owner,
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert exchange.sequence == 1 and chat.message_count == 1
    assert "secret-value" not in exchange.question
    assert "person@example.com" not in exchange.question
    assert exchange.citations == ["log-analysis://bms-001"]
    assert "association does not prove causality" in exchange.answer
    assert "no authority to change" in exchange.answer
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert "question" not in event.payload and "citations" not in event.payload

    replay, duplicate = await create_exchange(
        cast(AsyncSession, FakeSession([exchange])),
        conversation=chat,
        request=request,
        command=command,
        actor_user_id=owner,
        correlation_id=None,
    )
    assert replay is exchange and duplicate is True


@pytest.mark.asyncio
async def test_exchange_rejects_ungoverned_evidence_other_owner_expiry_and_limit() -> None:
    owner = uuid4()
    request = analysis_request(owner)
    base = AiChatExchangeCreate(
        exchange_id="grounded-exchange-002",
        question="Explain the failure evidence.",
        evidence_refs=["artifact://not-governed"],
    )
    with pytest.raises(AiChatContractError) as evidence_error:
        await create_exchange(
            cast(AsyncSession, FakeSession()),
            conversation=conversation(owner),
            request=request,
            command=base,
            actor_user_id=owner,
            correlation_id=None,
        )
    assert evidence_error.value.details == {
        "reason": "every citation must be governed by the analysis request"
    }
    with pytest.raises(ResourceNotFoundError):
        await create_exchange(
            cast(AsyncSession, FakeSession()),
            conversation=conversation(owner),
            request=request,
            command=base.model_copy(update={"evidence_refs": ["log-analysis://bms-001"]}),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    expired = conversation(owner)
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(AiChatContractError) as expired_error:
        await create_exchange(
            cast(AsyncSession, FakeSession()),
            conversation=expired,
            request=request,
            command=base.model_copy(update={"evidence_refs": ["log-analysis://bms-001"]}),
            actor_user_id=owner,
            correlation_id=None,
        )
    assert expired_error.value.details == {"reason": "the conversation is expired"}
    with pytest.raises(AiChatContractError) as limit_error:
        await create_exchange(
            cast(AsyncSession, FakeSession()),
            conversation=conversation(owner, count=50),
            request=request,
            command=base.model_copy(update={"evidence_refs": ["log-analysis://bms-001"]}),
            actor_user_id=owner,
            correlation_id=None,
        )
    assert limit_error.value.details == {
        "reason": "the conversation has reached the 50-exchange limit"
    }


def test_chat_models_preserve_retention_and_grounded_exchange_evidence() -> None:
    assert {"expires_at", "status", "message_count", "purged_at"} <= set(
        AiChatConversation.__table__.columns.keys()
    )
    assert {"question", "answer", "citations", "rule_version"} <= set(
        AiChatExchange.__table__.columns.keys()
    )


@pytest.mark.asyncio
async def test_expired_purge_removes_content_and_retains_minimized_evidence() -> None:
    owner = uuid4()
    expired = conversation(owner, count=2)
    expired.expires_at = datetime.now(UTC) - timedelta(days=1)
    session = FakeSession(scalar_results=[2], scalars_results=[[expired]])
    result = await purge_expired(
        cast(AsyncSession, session),
        actor_user_id=owner,
        correlation_id=uuid4(),
    )
    assert result.purged_conversation_count == 1
    assert result.purged_exchange_count == 2
    assert expired.status == "expired" and expired.message_count == 0
    assert expired.purged_at is not None and len(session.executed) == 1
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.ai.chat.expired.v1"
    assert event.payload == {"conversation_id": "grounded-chat-001", "status": "expired"}
