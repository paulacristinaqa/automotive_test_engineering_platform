from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import AiAnalysisRequest, AiTestSuggestion
from atep.ai_engine.schemas import (
    AiTestSuggestionCreate,
    AiTestSuggestionPromote,
    AiTestSuggestionReview,
)
from atep.ai_engine.test_generation import (
    create_suggestion,
    promote_suggestion,
    review_suggestion,
)
from atep.audit.models import AuditRecord
from atep.core.errors import AiTestSuggestionConflictError, AiTestSuggestionStateError
from atep.events.models import OutboxEvent
from atep.test_catalog.models import TestDefinition as CatalogDefinition


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
    def __init__(self, scalar_results: list[object | None] | None = None) -> None:
        self.scalar_results = list(scalar_results or [])
        self.added: list[Any] = []
        self.refreshed: list[tuple[Any, list[str]]] = []

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

    async def refresh(self, value: Any, attribute_names: list[str]) -> None:
        self.refreshed.append((value, attribute_names))
        if "updated_at" in attribute_names:
            value.updated_at = datetime.now(UTC)


def request(*, task: str = "test_suggestion") -> AiAnalysisRequest:
    return AiAnalysisRequest(
        id=uuid4(),
        request_id="ai-test-suggestion-001",
        request_hash="a" * 64,
        requested_by_user_id=uuid4(),
        task=task,
        subject_type="test_run",
        subject_id="test-run-001",
        provider_policy="local_only",
        data_classification="internal",
        evidence_refs=["log-analysis://log-analysis-001"],
        context={},
        instructions="Create a reviewable draft only.",
        status="queued",
        attempt_count=0,
    )


def command() -> AiTestSuggestionCreate:
    return AiTestSuggestionCreate(
        suggestion_id="test-suggestion-001",
        requirement_refs=["AI-F-022", "EV-F-THERMAL-001"],
        evidence_refs=["artifact://bms-regression-log"],
        name="BMS thermal anomaly regression",
        objective="Raise battery temperature and verify warning and diagnostic evidence.",
        domain="electric_vehicle",
        level="system",
        automation_mode="hybrid",
        timeout_seconds=600,
    )


def test_suggestion_contract_requires_bounded_requirement_evidence() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        command().model_copy(update={"requirement_refs": []}).model_validate(
            command().model_dump() | {"requirement_refs": []}
        )
    with pytest.raises(ValidationError, match="unique"):
        AiTestSuggestionCreate(**(command().model_dump() | {"requirement_refs": ["R1", "R1"]}))


@pytest.mark.asyncio
async def test_create_suggestion_is_deterministic_bounded_and_audited() -> None:
    session = FakeSession()
    suggestion, duplicate = await create_suggestion(
        cast(AsyncSession, session),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert suggestion.status == "draft"
    assert suggestion.version == 1
    assert suggestion.requirement_refs == ["AI-F-022", "EV-F-THERMAL-001"]
    assert suggestion.evidence_refs == [
        "log-analysis://log-analysis-001",
        "artifact://bms-regression-log",
    ]
    assert [step["step_id"] for step in suggestion.candidate["steps"]] == [
        "establish-baseline",
        "exercise-objective",
    ]
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.ai.test_suggestion.created.v1"
    assert "candidate" not in event.payload
    assert "objective" not in event.payload
    assert next(item for item in session.added if isinstance(item, AuditRecord)).action == (
        "ai_test_suggestion.created"
    )


@pytest.mark.asyncio
async def test_suggestion_replay_conflict_and_task_policy() -> None:
    original, _ = await create_suggestion(
        cast(AsyncSession, FakeSession()),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    replay, duplicate = await create_suggestion(
        cast(AsyncSession, FakeSession([original])),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert replay is original
    assert duplicate is True
    with pytest.raises(AiTestSuggestionConflictError):
        await create_suggestion(
            cast(AsyncSession, FakeSession([original])),
            request=request(),
            command=command().model_copy(update={"name": "Changed"}),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    with pytest.raises(AiTestSuggestionStateError, match="current state"):
        await create_suggestion(
            cast(AsyncSession, FakeSession()),
            request=request(task="log_analysis"),
            command=command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_review_requires_draft_version_and_preserves_rejection_evidence() -> None:
    suggestion, _ = await create_suggestion(
        cast(AsyncSession, FakeSession()),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    reviewer = uuid4()
    review_session = FakeSession()
    reviewed, duplicate = await review_suggestion(
        cast(AsyncSession, review_session),
        suggestion=suggestion,
        request=request(),
        command=AiTestSuggestionReview(
            expected_version=1,
            decision="reject",
            comment="Requirement EV-F-THERMAL-001 needs a precise temperature threshold.",
        ),
        actor_user_id=reviewer,
        correlation_id=None,
    )
    assert duplicate is False
    assert reviewed.status == "rejected"
    assert reviewed.version == 2
    assert reviewed.reviewed_by_user_id == reviewer
    assert "temperature threshold" in str(reviewed.review_comment)
    assert review_session.refreshed == [(reviewed, ["updated_at"])]
    with pytest.raises(AiTestSuggestionStateError):
        await review_suggestion(
            cast(AsyncSession, FakeSession()),
            suggestion=reviewed,
            request=request(),
            command=AiTestSuggestionReview(
                expected_version=2, decision="approve", comment="Approve after rejection."
            ),
            actor_user_id=reviewer,
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_promotion_requires_approval_and_creates_only_a_draft_catalog_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suggestion, _ = await create_suggestion(
        cast(AsyncSession, FakeSession()),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    with pytest.raises(AiTestSuggestionStateError):
        await promote_suggestion(
            cast(AsyncSession, FakeSession()),
            suggestion=suggestion,
            request=request(),
            command=AiTestSuggestionPromote(
                expected_version=1, definition_id="bms-thermal-regression"
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    suggestion.status = "approved"
    suggestion.version = 2
    created: list[Any] = []

    async def fake_create_definition(session: Any, **kwargs: Any) -> tuple[CatalogDefinition, bool]:
        definition = CatalogDefinition(
            id=uuid4(),
            created_by_user_id=kwargs["actor_user_id"],
            status="draft",
            version=1,
            **kwargs["command"].model_dump(mode="json"),
        )
        created.append(definition)
        return definition, False

    monkeypatch.setattr("atep.ai_engine.test_generation.create_definition", fake_create_definition)
    promotion_session = FakeSession()
    promoted, duplicate = await promote_suggestion(
        cast(AsyncSession, promotion_session),
        suggestion=suggestion,
        request=request(),
        command=AiTestSuggestionPromote(expected_version=2, definition_id="bms-thermal-regression"),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is False
    assert promoted.status == "promoted"
    assert promoted.version == 3
    assert promoted.promoted_definition_id == created[0].id
    assert promoted.promoted_definition_external_id == "bms-thermal-regression"
    assert created[0].status == "draft"
    assert promotion_session.refreshed == [(promoted, ["updated_at"])]


def test_suggestion_model_preserves_review_and_promotion_evidence() -> None:
    assert {
        "suggestion_id",
        "input_hash",
        "requirement_refs",
        "candidate",
        "review_comment",
        "reviewed_at",
        "promoted_definition_id",
    } <= set(AiTestSuggestion.__table__.columns.keys())
