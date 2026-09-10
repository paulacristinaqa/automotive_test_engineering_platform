import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.ai_engine.models import AiAnalysisRequest, AiTestSuggestion
from atep.ai_engine.schemas import (
    AiTestSuggestionCreate,
    AiTestSuggestionPromote,
    AiTestSuggestionResponse,
    AiTestSuggestionReview,
)
from atep.audit.service import record_audit
from atep.core.errors import (
    AiTestSuggestionConflictError,
    AiTestSuggestionStateError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event
from atep.test_catalog.schemas import TestDefinitionCreate, TestStep
from atep.test_catalog.service import create_definition


def _input_hash(request: AiAnalysisRequest, command: AiTestSuggestionCreate) -> str:
    payload = {"request_id": request.request_id, **command.model_dump(mode="json")}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def suggestion_response(
    suggestion: AiTestSuggestion,
    *,
    request: AiAnalysisRequest,
    duplicate: bool = False,
) -> AiTestSuggestionResponse:
    return AiTestSuggestionResponse(
        id=suggestion.id,
        suggestion_id=suggestion.suggestion_id,
        request_id=request.request_id,
        requirement_refs=suggestion.requirement_refs,
        evidence_refs=suggestion.evidence_refs,
        candidate=suggestion.candidate,
        rationale=suggestion.rationale,
        status=suggestion.status,
        version=suggestion.version,
        duplicate=duplicate,
        created_by_user_id=suggestion.created_by_user_id,
        reviewed_by_user_id=suggestion.reviewed_by_user_id,
        review_comment=suggestion.review_comment,
        reviewed_at=suggestion.reviewed_at,
        promoted_definition_id=suggestion.promoted_definition_id,
        promoted_definition_external_id=suggestion.promoted_definition_external_id,
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )


async def create_suggestion(
    session: AsyncSession,
    *,
    request: AiAnalysisRequest,
    command: AiTestSuggestionCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AiTestSuggestion, bool]:
    input_hash = _input_hash(request, command)
    existing = await session.scalar(
        select(AiTestSuggestion).where(AiTestSuggestion.suggestion_id == command.suggestion_id)
    )
    if existing is not None:
        if existing.input_hash == input_hash:
            return existing, True
        raise AiTestSuggestionConflictError()
    if request.task != "test_suggestion":
        raise AiTestSuggestionStateError("the analysis request task must be test_suggestion")
    existing_for_request = await session.scalar(
        select(AiTestSuggestion).where(AiTestSuggestion.request_id == request.id)
    )
    if existing_for_request is not None:
        raise AiTestSuggestionStateError("the request already has a test suggestion")

    evidence_refs = list(dict.fromkeys([*request.evidence_refs, *command.evidence_refs]))[:50]
    candidate = {
        "name": command.name.strip(),
        "description": command.objective.strip(),
        "domain": command.domain,
        "level": command.level,
        "automation_mode": command.automation_mode,
        "timeout_seconds": command.timeout_seconds,
        "tags": ["ai-suggested", "review-required"],
        "preconditions": [
            "Confirm the cited requirements and evidence are current and applicable.",
            "Use an isolated simulation environment with a known initial state.",
        ],
        "steps": [
            {
                "step_id": "establish-baseline",
                "action": "Establish the controlled baseline required by the cited requirements.",
                "target": request.subject_id,
                "inputs": {"mode": "controlled-simulation"},
                "expected": "The subject reports a known, healthy baseline before stimulation.",
            },
            {
                "step_id": "exercise-objective",
                "action": command.objective.strip(),
                "target": request.subject_id,
                "inputs": {"capture_evidence": True},
                "expected": (
                    "Observed behavior satisfies every cited requirement without a new severe "
                    "anomaly."
                ),
            },
        ],
    }
    suggestion = AiTestSuggestion(
        suggestion_id=command.suggestion_id,
        input_hash=input_hash,
        request_id=request.id,
        created_by_user_id=actor_user_id,
        requirement_refs=command.requirement_refs,
        evidence_refs=evidence_refs,
        candidate=candidate,
        rationale=(
            f"Draft derived deterministically from {len(command.requirement_refs)} requirement "
            f"reference(s) and {len(evidence_refs)} governed evidence reference(s). Human review "
            "is required."
        ),
        status="draft",
        version=1,
    )
    try:
        async with session.begin_nested():
            session.add(suggestion)
            await session.flush()
    except IntegrityError as exc:
        raise AiTestSuggestionConflictError() from exc
    _record(
        session,
        suggestion=suggestion,
        request=request,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        event="created",
    )
    return suggestion, False


async def review_suggestion(
    session: AsyncSession,
    *,
    suggestion: AiTestSuggestion,
    request: AiAnalysisRequest,
    command: AiTestSuggestionReview,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AiTestSuggestion, bool]:
    target = "approved" if command.decision == "approve" else "rejected"
    if suggestion.status == target and suggestion.review_comment == command.comment.strip():
        return suggestion, True
    if suggestion.status != "draft":
        raise AiTestSuggestionStateError("only a draft suggestion may be reviewed")
    if suggestion.version != command.expected_version:
        raise AiTestSuggestionStateError("the expected version does not match")
    suggestion.status = target
    suggestion.version += 1
    suggestion.reviewed_by_user_id = actor_user_id
    suggestion.review_comment = command.comment.strip()
    suggestion.reviewed_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(suggestion, attribute_names=["updated_at"])
    _record(
        session,
        suggestion=suggestion,
        request=request,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        event=target,
    )
    return suggestion, False


async def promote_suggestion(
    session: AsyncSession,
    *,
    suggestion: AiTestSuggestion,
    request: AiAnalysisRequest,
    command: AiTestSuggestionPromote,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AiTestSuggestion, bool]:
    if suggestion.status == "promoted":
        if suggestion.promoted_definition_external_id == command.definition_id:
            return suggestion, True
        raise AiTestSuggestionConflictError()
    if suggestion.status != "approved":
        raise AiTestSuggestionStateError("only an approved suggestion may be promoted")
    if suggestion.version != command.expected_version:
        raise AiTestSuggestionStateError("the expected version does not match")
    candidate = suggestion.candidate
    definition_command = TestDefinitionCreate(
        definition_id=command.definition_id,
        name=candidate["name"],
        description=candidate["description"],
        domain=candidate["domain"],
        level=candidate["level"],
        automation_mode=candidate["automation_mode"],
        timeout_seconds=candidate["timeout_seconds"],
        tags=candidate["tags"],
        preconditions=candidate["preconditions"],
        steps=[TestStep.model_validate(item) for item in candidate["steps"]],
    )
    definition, _ = await create_definition(
        session,
        command=definition_command,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
    )
    suggestion.promoted_definition_id = definition.id
    suggestion.promoted_definition_external_id = definition.definition_id
    suggestion.status = "promoted"
    suggestion.version += 1
    await session.flush()
    await session.refresh(suggestion, attribute_names=["updated_at"])
    _record(
        session,
        suggestion=suggestion,
        request=request,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        event="promoted",
        definition_id=definition.definition_id,
    )
    return suggestion, False


async def require_suggestion(
    session: AsyncSession, suggestion_id: str, *, for_update: bool = False
) -> tuple[AiTestSuggestion, AiAnalysisRequest]:
    query = (
        select(AiTestSuggestion, AiAnalysisRequest)
        .join(AiAnalysisRequest, AiAnalysisRequest.id == AiTestSuggestion.request_id)
        .where(AiTestSuggestion.suggestion_id == suggestion_id)
    )
    if for_update:
        query = query.with_for_update()
    row = (await session.execute(query)).one_or_none()
    if row is None:
        raise ResourceNotFoundError("ai_test_suggestion")
    return row[0], row[1]


async def list_suggestions(
    session: AsyncSession, *, limit: int, offset: int, status: str | None
) -> tuple[list[tuple[AiTestSuggestion, AiAnalysisRequest]], int]:
    filters = [] if status is None else [AiTestSuggestion.status == status]
    total = await session.scalar(select(func.count(AiTestSuggestion.id)).where(*filters))
    rows = await session.execute(
        select(AiTestSuggestion, AiAnalysisRequest)
        .join(AiAnalysisRequest, AiAnalysisRequest.id == AiTestSuggestion.request_id)
        .where(*filters)
        .order_by(AiTestSuggestion.created_at.desc(), AiTestSuggestion.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.tuples()), int(total or 0)


def _record(
    session: AsyncSession,
    *,
    suggestion: AiTestSuggestion,
    request: AiAnalysisRequest,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    event: str,
    definition_id: str | None = None,
) -> None:
    evidence: dict[str, object] = {
        "suggestion_id": suggestion.suggestion_id,
        "request_id": request.request_id,
        "status": suggestion.status,
        "version": suggestion.version,
        "requirement_count": len(suggestion.requirement_refs),
        "evidence_count": len(suggestion.evidence_refs),
    }
    if definition_id is not None:
        evidence["definition_id"] = definition_id
    enqueue_event(
        session,
        event_type=f"atep.ai.test_suggestion.{event}.v1",
        aggregate_type="ai_test_suggestion",
        aggregate_id=suggestion.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action=f"ai_test_suggestion.{event}",
        resource_type="ai_test_suggestion",
        resource_id=suggestion.id,
        details=evidence,
        correlation_id=correlation_id,
    )
