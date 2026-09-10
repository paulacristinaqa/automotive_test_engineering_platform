from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.evidence_projection import create_projection
from atep.ai_engine.models import (
    AiAnalysisRequest,
    AiChatConversation,
    AiChatExchange,
    AiEvidenceProjection,
    AiRootCauseRiskAnalysis,
)
from atep.ai_engine.schemas import AiEvidenceProjectionCreate
from atep.audit.models import AuditRecord
from atep.core.errors import AiEvidenceProjectionConflictError, ResourceNotFoundError
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


class Result:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def one_or_none(self) -> object | None:
        return self.value


class FakeSession:
    def __init__(
        self,
        *,
        execute_results: list[object | None],
        scalar_results: list[object | None] | None = None,
    ) -> None:
        self.execute_results = list(execute_results)
        self.scalar_results = list(scalar_results or [])
        self.added: list[Any] = []

    async def execute(self, _: Any) -> Result:
        return Result(self.execute_results.pop(0))

    async def scalar(self, _: Any) -> object | None:
        return self.scalar_results.pop(0) if self.scalar_results else None

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


def request(owner: UUID) -> AiAnalysisRequest:
    return AiAnalysisRequest(
        id=uuid4(),
        request_id="ai-evidence-request-001",
        request_hash="a" * 64,
        requested_by_user_id=owner,
        task="root_cause",
        subject_type="test_run",
        subject_id="test-run-001",
        provider_policy="local_only",
        data_classification="internal",
        evidence_refs=["artifact://bms-log"],
        context={},
        instructions="",
        status="succeeded",
        attempt_count=1,
    )


def root_risk(owner: UUID, request_id: UUID) -> AiRootCauseRiskAnalysis:
    return AiRootCauseRiskAnalysis(
        id=uuid4(),
        analysis_id="root-risk-analysis-001",
        input_hash="b" * 64,
        request_id=request_id,
        created_by_user_id=owner,
        horizon_hours=24,
        signals=[],
        hypotheses=[
            {
                "rank": 1,
                "code": "BMS_OVERHEAT",
                "component": "bms",
                "statement": "BMS thermal state is a candidate contributor.",
                "support_score": 80,
                "evidence_refs": ["artifact://bms-log"],
                "limitations": ["Association does not prove causality."],
            }
        ],
        risk_score=82,
        risk_band="critical",
        predicted_failure=True,
        limitations=[],
        version=1,
    )


def command(**updates: str) -> AiEvidenceProjectionCreate:
    values = {
        "projection_id": "ai-evidence-projection-001",
        "consumer": "carsystemui",
        "source_type": "root_cause_risk",
        "source_id": "root-risk-analysis-001",
        **updates,
    }
    return AiEvidenceProjectionCreate.model_validate(values)


def test_projection_contract_allows_only_known_consumers_and_sources() -> None:
    with pytest.raises(ValidationError):
        command(consumer="unknown")
    with pytest.raises(ValidationError):
        command(source_type="vehicle_command")


@pytest.mark.asyncio
async def test_projection_derives_allowlisted_cited_read_only_card() -> None:
    owner = uuid4()
    analysis_request = request(owner)
    analysis = root_risk(owner, analysis_request.id)
    session = FakeSession(execute_results=[(analysis, analysis_request)])
    projection, returned_request, duplicate = await create_projection(
        cast(AsyncSession, session),
        command=command(),
        actor_user_id=owner,
        correlation_id=uuid4(),
    )
    assert returned_request is analysis_request and duplicate is False
    assert projection.consumer == "carsystemui"
    assert projection.severity == "critical"
    assert projection.headline == "Critical risk score 82"
    assert projection.citations == ["artifact://bms-log"]
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.ai.evidence_projection.created.v1"
    assert "summary" not in event.payload and "citations" not in event.payload
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert audit.action == "ai_evidence_projection.created"


@pytest.mark.asyncio
async def test_projection_replay_and_changed_identifier_conflict() -> None:
    owner = uuid4()
    analysis_request = request(owner)
    analysis = root_risk(owner, analysis_request.id)
    original, _, _ = await create_projection(
        cast(AsyncSession, FakeSession(execute_results=[(analysis, analysis_request)])),
        command=command(),
        actor_user_id=owner,
        correlation_id=None,
    )
    replay, _, duplicate = await create_projection(
        cast(
            AsyncSession,
            FakeSession(execute_results=[(analysis, analysis_request)], scalar_results=[original]),
        ),
        command=command(),
        actor_user_id=owner,
        correlation_id=None,
    )
    assert replay is original and duplicate is True
    with pytest.raises(AiEvidenceProjectionConflictError):
        await create_projection(
            cast(
                AsyncSession,
                FakeSession(
                    execute_results=[(analysis, analysis_request)], scalar_results=[original]
                ),
            ),
            command=command(consumer="dashboard"),
            actor_user_id=owner,
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_chat_projection_preserves_owner_boundary() -> None:
    owner = uuid4()
    analysis_request = request(owner)
    conversation = AiChatConversation(
        id=uuid4(),
        conversation_id="grounded-chat-001",
        creation_hash="c" * 64,
        request_id=analysis_request.id,
        owner_user_id=owner,
        title="Private",
        retention_days=7,
        expires_at=datetime.now(UTC),
        status="active",
        message_count=1,
    )
    exchange = AiChatExchange(
        id=uuid4(),
        exchange_id="grounded-exchange-001",
        exchange_hash="d" * 64,
        conversation_id=conversation.id,
        created_by_user_id=owner,
        sequence=1,
        question="What happened?",
        answer="Review the governed evidence.",
        citations=["artifact://bms-log"],
        rule_version="grounded-chat-rules-v1",
        limitations=[],
    )
    with pytest.raises(ResourceNotFoundError):
        await create_projection(
            cast(
                AsyncSession,
                FakeSession(execute_results=[(exchange, conversation, analysis_request)]),
            ),
            command=command(source_type="chat_exchange", source_id="grounded-exchange-001"),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


def test_projection_model_is_immutable_allowlisted_evidence() -> None:
    assert {
        "consumer",
        "source_type",
        "source_id",
        "subject_type",
        "subject_id",
        "headline",
        "summary",
        "citations",
        "contract_version",
    } <= set(AiEvidenceProjection.__table__.columns.keys())
