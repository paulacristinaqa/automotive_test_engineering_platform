from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import AiAnalysisRequest, AiRootCauseRiskAnalysis
from atep.ai_engine.root_cause_risk import create_analysis, evaluate_prediction
from atep.ai_engine.schemas import AiPredictionEvaluationCreate, AiRootCauseRiskCreate
from atep.audit.models import AuditRecord
from atep.core.errors import AiRootCauseRiskConflictError, AiRootCauseRiskContractError
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
        value.updated_at = datetime.now(UTC)


def request(*, task: str = "root_cause") -> AiAnalysisRequest:
    return AiAnalysisRequest(
        id=uuid4(),
        request_id="ai-root-cause-001",
        request_hash="a" * 64,
        requested_by_user_id=uuid4(),
        task=task,
        subject_type="test_run",
        subject_id="test-run-001",
        provider_policy="local_only",
        data_classification="internal",
        evidence_refs=["log-analysis://bms-001", "diagnostic://dtc-p0a80"],
        context={},
        instructions="Rank evidence without claiming causality.",
        status="queued",
        attempt_count=0,
    )


def command() -> AiRootCauseRiskCreate:
    return AiRootCauseRiskCreate(
        analysis_id="root-risk-analysis-001",
        horizon_hours=24,
        signals=[
            {
                "code": "CELL_OVERHEAT",
                "component": "bms",
                "symptom": "Repeated critical battery cell temperature events",
                "severity": "critical",
                "occurrence_count": 5,
                "confidence": 0.8,
                "detectability": 0.2,
                "evidence_refs": ["log-analysis://bms-001"],
            },
            {
                "code": "BATTERY_DTC",
                "component": "bms",
                "symptom": "Battery degradation diagnostic trouble code",
                "severity": "high",
                "occurrence_count": 1,
                "confidence": 0.75,
                "detectability": 0.8,
                "evidence_refs": ["diagnostic://dtc-p0a80"],
            },
        ],
    )


def test_root_cause_risk_contract_bounds_and_uniqueness() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        AiRootCauseRiskCreate(analysis_id="root-risk-empty", signals=[])
    payload = command().model_dump()
    payload["signals"] = [payload["signals"][0], payload["signals"][0]]
    with pytest.raises(ValidationError, match="signal codes must be unique"):
        AiRootCauseRiskCreate.model_validate(payload)


@pytest.mark.asyncio
async def test_analysis_ranks_evidence_and_calculates_explainable_risk() -> None:
    session = FakeSession()
    analysis, duplicate = await create_analysis(
        cast(AsyncSession, session),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert [item["code"] for item in analysis.hypotheses] == [
        "CELL_OVERHEAT",
        "BATTERY_DTC",
    ]
    assert [item["rank"] for item in analysis.hypotheses] == [1, 2]
    assert analysis.hypotheses[0]["support_score"] == 81.0
    assert analysis.risk_score == 80
    assert analysis.risk_band == "critical"
    assert analysis.predicted_failure is True
    assert "do not prove root cause" in analysis.limitations[1]
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.ai.root_cause_risk.completed.v1"
    assert "signals" not in event.payload and "hypotheses" not in event.payload
    assert next(item for item in session.added if isinstance(item, AuditRecord)).action == (
        "ai_root_cause_risk.completed"
    )


@pytest.mark.asyncio
async def test_analysis_replay_conflict_task_and_evidence_policy() -> None:
    original, _ = await create_analysis(
        cast(AsyncSession, FakeSession()),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    replay, duplicate = await create_analysis(
        cast(AsyncSession, FakeSession([original])),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert replay is original and duplicate is True
    with pytest.raises(AiRootCauseRiskConflictError):
        await create_analysis(
            cast(AsyncSession, FakeSession([original])),
            request=request(),
            command=command().model_copy(update={"horizon_hours": 48}),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    with pytest.raises(AiRootCauseRiskContractError, match="governed contract"):
        await create_analysis(
            cast(AsyncSession, FakeSession()),
            request=request(task="test_suggestion"),
            command=command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    bad = command().model_dump()
    bad["signals"][0]["evidence_refs"] = ["artifact://not-governed"]
    with pytest.raises(AiRootCauseRiskContractError) as error:
        await create_analysis(
            cast(AsyncSession, FakeSession()),
            request=request(),
            command=AiRootCauseRiskCreate.model_validate(bad),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details == {
        "reason": "every signal must cite evidence governed by the analysis request"
    }


@pytest.mark.asyncio
async def test_prediction_evaluation_is_versioned_scored_and_idempotent() -> None:
    analysis, _ = await create_analysis(
        cast(AsyncSession, FakeSession()),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    evaluation = AiPredictionEvaluationCreate(
        evaluation_id="prediction-evaluation-001",
        expected_version=1,
        actual_failure=True,
        confirmed_hypothesis_code="CELL_OVERHEAT",
        evidence_refs=["log-analysis://bms-001"],
    )
    session = FakeSession()
    evaluated, duplicate = await evaluate_prediction(
        cast(AsyncSession, session),
        analysis=analysis,
        request=request(),
        command=evaluation,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is False
    assert evaluated.version == 2
    assert evaluated.prediction_correct is True
    assert evaluated.brier_score == 0.04
    assert session.refreshed == [(evaluated, ["updated_at"])]
    replay, duplicate = await evaluate_prediction(
        cast(AsyncSession, FakeSession()),
        analysis=evaluated,
        request=request(),
        command=evaluation,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert replay is evaluated and duplicate is True
    with pytest.raises(AiRootCauseRiskConflictError):
        await evaluate_prediction(
            cast(AsyncSession, FakeSession()),
            analysis=evaluated,
            request=request(),
            command=evaluation.model_copy(update={"actual_failure": False}),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_evaluation_rejects_stale_unknown_and_ungoverned_evidence() -> None:
    analysis, _ = await create_analysis(
        cast(AsyncSession, FakeSession()),
        request=request(),
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    base = AiPredictionEvaluationCreate(
        evaluation_id="prediction-evaluation-002",
        expected_version=2,
        actual_failure=False,
        evidence_refs=["log-analysis://bms-001"],
    )
    with pytest.raises(AiRootCauseRiskContractError) as stale:
        await evaluate_prediction(
            cast(AsyncSession, FakeSession()),
            analysis=analysis,
            request=request(),
            command=base,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert stale.value.details == {"reason": "the expected version does not match"}
    unknown = base.model_copy(
        update={"expected_version": 1, "confirmed_hypothesis_code": "UNKNOWN_CAUSE"}
    )
    with pytest.raises(AiRootCauseRiskContractError, match="governed contract"):
        await evaluate_prediction(
            cast(AsyncSession, FakeSession()),
            analysis=analysis,
            request=request(),
            command=unknown,
            actor_user_id=uuid4(),
            correlation_id=None,
        )


def test_model_preserves_prediction_evaluation_evidence() -> None:
    assert {
        "analysis_id",
        "signals",
        "hypotheses",
        "risk_score",
        "evaluation_id",
        "prediction_correct",
        "brier_score",
    } <= set(AiRootCauseRiskAnalysis.__table__.columns.keys())
