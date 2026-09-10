import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import AiAnalysisRequest, AiRootCauseRiskAnalysis
from atep.ai_engine.schemas import (
    AiPredictionEvaluationCreate,
    AiPredictionMetrics,
    AiRootCauseRiskCreate,
    AiRootCauseRiskResponse,
)
from atep.audit.service import record_audit
from atep.core.errors import (
    AiRootCauseRiskConflictError,
    AiRootCauseRiskContractError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event

SEVERITY_WEIGHT = {"info": 5, "low": 15, "medium": 35, "high": 65, "critical": 90}
SUPPORTED_TASKS = {"root_cause", "risk_analysis"}


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _rank_hypotheses(command: AiRootCauseRiskCreate) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for signal in command.signals:
        severity = SEVERITY_WEIGHT[signal.severity]
        frequency_factor = 0.8 + 0.2 * min(signal.occurrence_count / 5, 1)
        confidence_factor = 0.5 + 0.5 * signal.confidence
        support = round(severity * frequency_factor * confidence_factor, 2)
        candidates.append(
            {
                "rank": 0,
                "code": signal.code,
                "component": signal.component,
                "statement": (
                    f"{signal.component} is a candidate contributor associated with the observed "
                    f"symptom: {signal.symptom}"
                ),
                "support_score": support,
                "evidence_refs": signal.evidence_refs,
                "limitations": [
                    "Association does not prove causality.",
                    "A reviewer must validate the hypothesis against vehicle state and "
                    "requirements.",
                ],
            }
        )
    candidates.sort(key=lambda item: (-float(item["support_score"]), str(item["code"])))
    for rank, item in enumerate(candidates, start=1):
        item["rank"] = rank
    return candidates


def _risk(command: AiRootCauseRiskCreate, hypotheses: list[dict[str, Any]]) -> tuple[int, str]:
    probability = float(hypotheses[0]["support_score"])
    impact = max(SEVERITY_WEIGHT[item.severity] for item in command.signals)
    detectability = sum(item.detectability for item in command.signals) / len(command.signals)
    score = round(0.45 * probability + 0.4 * impact + 0.15 * (100 - detectability * 100))
    score = max(0, min(100, score))
    band = "low" if score < 25 else "medium" if score < 50 else "high" if score < 75 else "critical"
    return score, band


def analysis_response(
    analysis: AiRootCauseRiskAnalysis,
    *,
    request: AiAnalysisRequest,
    duplicate: bool = False,
) -> AiRootCauseRiskResponse:
    return AiRootCauseRiskResponse(
        id=analysis.id,
        analysis_id=analysis.analysis_id,
        request_id=request.request_id,
        horizon_hours=analysis.horizon_hours,
        signals=analysis.signals,
        hypotheses=analysis.hypotheses,
        risk_score=analysis.risk_score,
        risk_band=analysis.risk_band,
        predicted_failure=analysis.predicted_failure,
        limitations=analysis.limitations,
        version=analysis.version,
        duplicate=duplicate,
        created_by_user_id=analysis.created_by_user_id,
        evaluation_id=analysis.evaluation_id,
        evaluated_by_user_id=analysis.evaluated_by_user_id,
        actual_failure=analysis.actual_failure,
        confirmed_hypothesis_code=analysis.confirmed_hypothesis_code,
        evaluation_evidence_refs=analysis.evaluation_evidence_refs,
        prediction_correct=analysis.prediction_correct,
        brier_score=analysis.brier_score,
        evaluated_at=analysis.evaluated_at,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
    )


async def create_analysis(
    session: AsyncSession,
    *,
    request: AiAnalysisRequest,
    command: AiRootCauseRiskCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AiRootCauseRiskAnalysis, bool]:
    input_hash = _hash({"request_id": request.request_id, **command.model_dump(mode="json")})
    existing = await session.scalar(
        select(AiRootCauseRiskAnalysis).where(
            AiRootCauseRiskAnalysis.analysis_id == command.analysis_id
        )
    )
    if existing is not None:
        if existing.input_hash == input_hash:
            return existing, True
        raise AiRootCauseRiskConflictError()
    if request.task not in SUPPORTED_TASKS:
        raise AiRootCauseRiskContractError("the request task must be root_cause or risk_analysis")
    existing_for_request = await session.scalar(
        select(AiRootCauseRiskAnalysis).where(AiRootCauseRiskAnalysis.request_id == request.id)
    )
    if existing_for_request is not None:
        raise AiRootCauseRiskContractError("the request already has a root cause and risk analysis")
    allowed_evidence = set(request.evidence_refs)
    supplied_evidence = {ref for signal in command.signals for ref in signal.evidence_refs}
    if not supplied_evidence <= allowed_evidence:
        raise AiRootCauseRiskContractError(
            "every signal must cite evidence governed by the analysis request"
        )
    hypotheses = _rank_hypotheses(command)
    risk_score, risk_band = _risk(command, hypotheses)
    analysis = AiRootCauseRiskAnalysis(
        analysis_id=command.analysis_id,
        input_hash=input_hash,
        request_id=request.id,
        created_by_user_id=actor_user_id,
        horizon_hours=command.horizon_hours,
        signals=[item.model_dump(mode="json") for item in command.signals],
        hypotheses=hypotheses,
        risk_score=risk_score,
        risk_band=risk_band,
        predicted_failure=risk_score >= 50,
        limitations=[
            "Scores are deterministic prioritization aids, not calibrated safety probabilities.",
            "Ranked associations do not prove root cause.",
            "No result may mutate vehicle, catalog, schedule, or test execution state.",
        ],
        version=1,
    )
    try:
        async with session.begin_nested():
            session.add(analysis)
            await session.flush()
    except IntegrityError as exc:
        raise AiRootCauseRiskConflictError() from exc
    _record(session, analysis, request, actor_user_id, correlation_id, "completed")
    return analysis, False


async def evaluate_prediction(
    session: AsyncSession,
    *,
    analysis: AiRootCauseRiskAnalysis,
    request: AiAnalysisRequest,
    command: AiPredictionEvaluationCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AiRootCauseRiskAnalysis, bool]:
    evaluation_hash = _hash(command.model_dump(mode="json", exclude={"expected_version"}))
    if analysis.evaluation_id is not None:
        if (
            analysis.evaluation_id == command.evaluation_id
            and analysis.evaluation_hash == evaluation_hash
        ):
            return analysis, True
        raise AiRootCauseRiskConflictError()
    if analysis.version != command.expected_version:
        raise AiRootCauseRiskContractError("the expected version does not match")
    if not set(command.evidence_refs) <= set(request.evidence_refs):
        raise AiRootCauseRiskContractError(
            "evaluation evidence must be governed by the analysis request"
        )
    hypothesis_codes = {str(item["code"]) for item in analysis.hypotheses}
    if (
        command.confirmed_hypothesis_code is not None
        and command.confirmed_hypothesis_code not in hypothesis_codes
    ):
        raise AiRootCauseRiskContractError(
            "the confirmed hypothesis was not ranked by this analysis"
        )
    probability = analysis.risk_score / 100
    outcome = 1.0 if command.actual_failure else 0.0
    analysis.evaluation_id = command.evaluation_id
    analysis.evaluation_hash = evaluation_hash
    analysis.evaluated_by_user_id = actor_user_id
    analysis.actual_failure = command.actual_failure
    analysis.confirmed_hypothesis_code = command.confirmed_hypothesis_code
    analysis.evaluation_evidence_refs = command.evidence_refs
    analysis.prediction_correct = analysis.predicted_failure == command.actual_failure
    analysis.brier_score = round((probability - outcome) ** 2, 4)
    analysis.evaluated_at = datetime.now(UTC)
    analysis.version += 1
    await session.flush()
    await session.refresh(analysis, attribute_names=["updated_at"])
    _record(session, analysis, request, actor_user_id, correlation_id, "evaluated")
    return analysis, False


async def require_analysis(
    session: AsyncSession, analysis_id: str, *, for_update: bool = False
) -> tuple[AiRootCauseRiskAnalysis, AiAnalysisRequest]:
    query = (
        select(AiRootCauseRiskAnalysis, AiAnalysisRequest)
        .join(AiAnalysisRequest, AiAnalysisRequest.id == AiRootCauseRiskAnalysis.request_id)
        .where(AiRootCauseRiskAnalysis.analysis_id == analysis_id)
    )
    if for_update:
        query = query.with_for_update()
    row = (await session.execute(query)).one_or_none()
    if row is None:
        raise ResourceNotFoundError("ai_root_cause_risk_analysis")
    return row[0], row[1]


async def list_analyses(
    session: AsyncSession, *, limit: int, offset: int, risk_band: str | None
) -> tuple[list[tuple[AiRootCauseRiskAnalysis, AiAnalysisRequest]], int]:
    filters = [] if risk_band is None else [AiRootCauseRiskAnalysis.risk_band == risk_band]
    total = await session.scalar(select(func.count(AiRootCauseRiskAnalysis.id)).where(*filters))
    rows = await session.execute(
        select(AiRootCauseRiskAnalysis, AiAnalysisRequest)
        .join(AiAnalysisRequest, AiAnalysisRequest.id == AiRootCauseRiskAnalysis.request_id)
        .where(*filters)
        .order_by(AiRootCauseRiskAnalysis.created_at.desc(), AiRootCauseRiskAnalysis.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.tuples()), int(total or 0)


async def prediction_metrics(session: AsyncSession) -> AiPredictionMetrics:
    row = (
        await session.execute(
            select(
                func.count(AiRootCauseRiskAnalysis.id),
                func.count(AiRootCauseRiskAnalysis.id).filter(
                    AiRootCauseRiskAnalysis.prediction_correct.is_(True)
                ),
                func.avg(AiRootCauseRiskAnalysis.brier_score),
            ).where(AiRootCauseRiskAnalysis.evaluation_id.is_not(None))
        )
    ).one()
    evaluated, correct, mean_brier = int(row[0] or 0), int(row[1] or 0), row[2]
    return AiPredictionMetrics(
        evaluated_count=evaluated,
        correct_count=correct,
        accuracy=round(correct / evaluated, 4) if evaluated else None,
        mean_brier_score=round(float(mean_brier), 4) if mean_brier is not None else None,
    )


def _record(
    session: AsyncSession,
    analysis: AiRootCauseRiskAnalysis,
    request: AiAnalysisRequest,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    action: str,
) -> None:
    evidence = {
        "analysis_id": analysis.analysis_id,
        "request_id": request.request_id,
        "risk_score": analysis.risk_score,
        "risk_band": analysis.risk_band,
        "hypothesis_count": len(analysis.hypotheses),
        "status": action,
        "version": analysis.version,
    }
    if action == "evaluated":
        evidence.update(
            {
                "prediction_correct": analysis.prediction_correct,
                "brier_score": analysis.brier_score,
            }
        )
    enqueue_event(
        session,
        event_type=f"atep.ai.root_cause_risk.{action}.v1",
        aggregate_type="ai_root_cause_risk_analysis",
        aggregate_id=analysis.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action=f"ai_root_cause_risk.{action}",
        resource_type="ai_root_cause_risk_analysis",
        resource_id=analysis.id,
        details=evidence,
        correlation_id=correlation_id,
    )
