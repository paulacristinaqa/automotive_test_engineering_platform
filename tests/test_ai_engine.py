from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import AiAnalysisRequest
from atep.ai_engine.schemas import (
    AiAnalysisRequestCreate,
    DataClassification,
    ProviderPolicy,
)
from atep.ai_engine.service import create_request
from atep.audit.models import AuditRecord
from atep.core.errors import AiAnalysisConflictError, AiAnalysisPolicyError
from atep.events.models import OutboxEvent
from atep.identity.permissions import PermissionName


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
    def __init__(self, existing: AiAnalysisRequest | None = None) -> None:
        self.existing = existing
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> AiAnalysisRequest | None:
        return self.existing

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()
            if getattr(value, "created_at", None) is None:
                value.created_at = datetime.now(UTC)


def command() -> AiAnalysisRequestCreate:
    return AiAnalysisRequestCreate(
        request_id="ai-analysis-001",
        task="root_cause",
        subject_type="automation_report",
        subject_id="automation-report-001",
        evidence_refs=["artifact://sanitized-log-001"],
        context={"dtc_codes": ["P0A80"]},
        instructions="Explain likely causes without inventing evidence.",
    )


def test_contract_bounds_context_and_evidence() -> None:
    payload = command().model_dump()
    payload["evidence_refs"] *= 2
    with pytest.raises(ValidationError, match="unique"):
        AiAnalysisRequestCreate(**payload)
    payload = command().model_dump()
    payload["context"] = {"value": "x" * 17_000}
    with pytest.raises(ValidationError, match="16384"):
        AiAnalysisRequestCreate(**payload)


@pytest.mark.asyncio
async def test_create_request_is_idempotent_and_minimizes_events() -> None:
    actor = uuid4()
    session = FakeSession()
    request, duplicate = await create_request(
        cast(AsyncSession, session), command=command(), actor_user_id=actor, correlation_id=uuid4()
    )
    assert duplicate is False
    assert request.provider_policy == "local_only"
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.ai.analysis.requested.v1"
    assert event.payload["evidence_ref_count"] == 1
    assert "context" not in event.payload
    assert (
        next(item for item in session.added if isinstance(item, AuditRecord)).action
        == "ai_analysis.requested"
    )
    replay, duplicate = await create_request(
        cast(AsyncSession, FakeSession(request)),
        command=command(),
        actor_user_id=actor,
        correlation_id=None,
    )
    assert replay is request
    assert duplicate is True


@pytest.mark.asyncio
async def test_policy_and_changed_replay_are_rejected() -> None:
    restricted = command()
    restricted.data_classification = DataClassification.RESTRICTED
    restricted.provider_policy = ProviderPolicy.EXTERNAL_ALLOWED
    with pytest.raises(AiAnalysisPolicyError):
        await create_request(
            cast(AsyncSession, FakeSession()),
            command=restricted,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    existing, _ = await create_request(
        cast(AsyncSession, FakeSession()),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    changed = command()
    changed.instructions = "Different"
    with pytest.raises(AiAnalysisConflictError):
        await create_request(
            cast(AsyncSession, FakeSession(existing)),
            command=changed,
            actor_user_id=uuid4(),
            correlation_id=None,
        )


def test_ai_permissions_are_explicit() -> None:
    assert PermissionName.AI_ANALYSIS_READ.value == "ai_analysis:read"
    assert PermissionName.AI_ANALYSIS_MANAGE.value == "ai_analysis:manage"
