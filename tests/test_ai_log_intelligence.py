from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.log_intelligence import create_log_analysis
from atep.ai_engine.models import AiAnalysisRequest, AiLogAnalysis
from atep.ai_engine.schemas import AiLogAnalysisCreate
from atep.audit.models import AuditRecord
from atep.core.errors import (
    AiLogAnalysisConflictError,
    AiLogAnalysisContractError,
)
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
    def __init__(self, scalar_results: list[object | None] | None = None) -> None:
        self.scalar_results = list(scalar_results or [])
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> object | None:
        return self.scalar_results.pop(0) if self.scalar_results else None

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


def request(*, task: str = "log_analysis") -> AiAnalysisRequest:
    return AiAnalysisRequest(
        id=uuid4(),
        request_id="ai-analysis-logs-001",
        request_hash="a" * 64,
        requested_by_user_id=uuid4(),
        task=task,
        subject_type="test_run",
        subject_id="test-run-001",
        provider_policy="local_only",
        data_classification="internal",
        evidence_refs=["artifact://sanitized-vehicle-log"],
        context={},
        instructions="Explain only supported signals.",
        status="queued",
        attempt_count=0,
    )


def command() -> AiLogAnalysisCreate:
    return AiLogAnalysisCreate(
        analysis_id="log-analysis-001",
        source="bms-ecu",
        lines=[
            "2026-09-10T10:00:02Z ERROR [bms] Cell voltage 2.1 token=private",
            (
                "2026-09-10T10:00:00Z INFO [bms] Boot completed for owner@example.com "
                "VIN 1HGCM82633A004352 Bearer abc.def"
            ),
            "not a supported log line",
            "2026-09-10T10:00:03Z ERROR [bms] Cell voltage 2.2 token=private",
            "2026-09-10T10:00:04Z ERROR [bms] Cell voltage 2.3 token=private",
        ],
    )


def test_log_batch_contract_is_bounded() -> None:
    with pytest.raises(ValidationError, match="500"):
        AiLogAnalysisCreate(
            analysis_id="log-analysis-large",
            source="gateway",
            lines=["x"] * 501,
        )
    with pytest.raises(ValidationError, match="2000"):
        AiLogAnalysisCreate(
            analysis_id="log-analysis-line",
            source="gateway",
            lines=["x" * 2001],
        )


@pytest.mark.asyncio
async def test_log_analysis_sanitizes_clusters_orders_and_explains() -> None:
    session = FakeSession()
    analysis, duplicate = await create_log_analysis(
        cast(AsyncSession, session),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert analysis.parsed_count == 4
    assert analysis.rejected_count == 1
    assert [item["line_number"] for item in analysis.timeline] == [2, 1, 4, 5]
    serialized = str(analysis.timeline)
    assert "private" not in serialized
    assert "owner@example.com" not in serialized
    assert "1HGCM82633A004352" not in serialized
    assert "abc.def" not in serialized
    error_cluster = next(item for item in analysis.clusters if item["count"] == 3)
    assert error_cluster["line_numbers"] == [1, 4, 5]
    assert {item["anomaly_type"] for item in analysis.anomalies} == {
        "severe_event",
        "burst",
    }
    assert analysis.explanation["supporting_line_numbers"] == [1, 4, 5]
    assert analysis.explanation["evidence_refs"] == ["artifact://sanitized-vehicle-log"]
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.ai.log_analysis.completed.v1"
    assert "timeline" not in event.payload
    assert "lines" not in event.payload
    assert (
        next(item for item in session.added if isinstance(item, AuditRecord)).action
        == "ai_log_analysis.completed"
    )


@pytest.mark.asyncio
async def test_log_analysis_replay_conflict_and_task_policy() -> None:
    original, _ = await create_log_analysis(
        cast(AsyncSession, FakeSession()),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    replay, duplicate = await create_log_analysis(
        cast(AsyncSession, FakeSession([original])),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert replay is original
    assert duplicate is True
    changed = command().model_copy(update={"source": "gateway"})
    with pytest.raises(AiLogAnalysisConflictError):
        await create_log_analysis(
            cast(AsyncSession, FakeSession([original])),
            request=request(),
            command=changed,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    with pytest.raises(AiLogAnalysisContractError) as task_error:
        await create_log_analysis(
            cast(AsyncSession, FakeSession()),
            request=request(task="test_suggestion"),
            command=command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert task_error.value.details == {
        "reason": "the request task does not support log intelligence"
    }


@pytest.mark.asyncio
async def test_log_analysis_rejects_unparseable_and_unbounded_timeline() -> None:
    unparseable = command().model_copy(update={"lines": ["plain text only"]})
    with pytest.raises(AiLogAnalysisContractError) as parse_error:
        await create_log_analysis(
            cast(AsyncSession, FakeSession()),
            request=request(),
            command=unparseable,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert parse_error.value.details == {"reason": "the batch contains no parseable log lines"}
    long_timeline = command().model_copy(
        update={
            "lines": [
                "2026-09-01T00:00:00Z INFO [gateway] Start",
                "2026-09-10T00:00:00Z ERROR [gateway] End",
            ]
        }
    )
    with pytest.raises(AiLogAnalysisContractError) as timeline_error:
        await create_log_analysis(
            cast(AsyncSession, FakeSession()),
            request=request(),
            command=long_timeline,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert timeline_error.value.details == {"reason": "the log timeline exceeds seven days"}


def test_log_analysis_model_preserves_immutable_evidence_fields() -> None:
    assert {
        "analysis_id",
        "input_hash",
        "timeline",
        "clusters",
        "anomalies",
        "explanation",
    } <= set(AiLogAnalysis.__table__.columns.keys())
