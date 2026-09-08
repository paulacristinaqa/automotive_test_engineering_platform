import json
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    FaultCampaignConflictError,
    FaultCampaignStateError,
    FaultCampaignVersionConflictError,
    FaultExecutionConflictError,
    FaultExecutionStateError,
    FaultExecutionVersionConflictError,
    FaultStepStateError,
    FaultStepVersionConflictError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event
from atep.fault_campaigns.models import FaultCampaign, FaultCampaignExecution, FaultStepResult
from atep.fault_campaigns.schemas import (
    FaultCampaignCreate,
    FaultCampaignResponse,
    FaultCampaignStatus,
    FaultCampaignStatusUpdate,
    FaultExecutionCancel,
    FaultExecutionCreate,
    FaultExecutionResponse,
    FaultExecutionStatus,
    FaultStepResultResponse,
    FaultStepResultUpdate,
    FaultStepStatus,
)
from atep.test_runs.models import TestRun
from atep.vehicles.models import Vehicle

CAMPAIGN_TRANSITIONS = {
    FaultCampaignStatus.DRAFT: {FaultCampaignStatus.ACTIVE},
    FaultCampaignStatus.ACTIVE: {FaultCampaignStatus.ARCHIVED},
    FaultCampaignStatus.ARCHIVED: set(),
}

STEP_TRANSITIONS = {
    FaultStepStatus.PENDING: {FaultStepStatus.INJECTING, FaultStepStatus.SKIPPED},
    FaultStepStatus.INJECTING: {FaultStepStatus.INJECTED, FaultStepStatus.FAILED},
    FaultStepStatus.INJECTED: {FaultStepStatus.RECOVERING, FaultStepStatus.FAILED},
    FaultStepStatus.RECOVERING: {FaultStepStatus.RECOVERED, FaultStepStatus.FAILED},
    FaultStepStatus.RECOVERED: set(),
    FaultStepStatus.FAILED: set(),
    FaultStepStatus.SKIPPED: set(),
}

TERMINAL_STEP_STATUSES = {
    FaultStepStatus.RECOVERED.value,
    FaultStepStatus.FAILED.value,
    FaultStepStatus.SKIPPED.value,
}


async def create_campaign(
    session: AsyncSession,
    *,
    command: FaultCampaignCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[FaultCampaign, bool]:
    existing = await session.scalar(
        select(FaultCampaign).where(FaultCampaign.campaign_id == command.campaign_id)
    )
    if existing is not None:
        if not _same_campaign_creation(existing, command, actor_user_id):
            raise FaultCampaignConflictError()
        return existing, True

    created_at = now or datetime.now(UTC)
    campaign = FaultCampaign(
        campaign_id=command.campaign_id,
        created_by_user_id=actor_user_id,
        name=command.name,
        description=command.description,
        blast_radius=command.blast_radius.value,
        steps=[
            item.model_dump(mode="json") for item in sorted(command.steps, key=lambda x: x.order)
        ],
        tags=command.tags,
        status=FaultCampaignStatus.DRAFT.value,
        version=1,
        created_at=created_at,
        updated_at=created_at,
    )
    await _persist(session, campaign, FaultCampaignConflictError())
    payload = campaign_event_payload(campaign)
    _record_evidence(
        session,
        resource=campaign,
        event_type="atep.fault_campaign.created.v1",
        action="fault_campaign.created",
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload=payload,
    )
    return campaign, False


async def require_campaign(
    session: AsyncSession, campaign_id: str, *, for_update: bool = False
) -> FaultCampaign:
    query = select(FaultCampaign).where(FaultCampaign.campaign_id == campaign_id)
    if for_update:
        query = query.with_for_update()
    campaign = await session.scalar(query)
    if campaign is None:
        raise ResourceNotFoundError("fault_campaign")
    return campaign


async def list_campaigns(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: FaultCampaignStatus | None,
) -> tuple[list[FaultCampaign], int]:
    query = select(FaultCampaign)
    if status is not None:
        query = query.where(FaultCampaign.status == status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(FaultCampaign.campaign_id).limit(limit).offset(offset)
    )
    return list(rows), int(total or 0)


async def update_campaign_status(
    session: AsyncSession,
    *,
    campaign: FaultCampaign,
    command: FaultCampaignStatusUpdate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[FaultCampaign, bool]:
    if campaign.status == command.status.value:
        return campaign, True
    if campaign.version != command.expected_version:
        raise FaultCampaignVersionConflictError(current_version=campaign.version)
    current = FaultCampaignStatus(campaign.status)
    if command.status not in CAMPAIGN_TRANSITIONS[current]:
        raise FaultCampaignStateError(
            current_status=current.value, requested_status=command.status.value
        )
    previous_status = campaign.status
    campaign.status = command.status.value
    campaign.version += 1
    await session.flush()
    await session.refresh(campaign, attribute_names=["updated_at"])
    payload = {**campaign_event_payload(campaign), "previous_status": previous_status}
    _record_evidence(
        session,
        resource=campaign,
        event_type="atep.fault_campaign.status_changed.v1",
        action="fault_campaign.status_changed",
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload=payload,
    )
    return campaign, False


async def create_execution(
    session: AsyncSession,
    *,
    campaign: FaultCampaign,
    command: FaultExecutionCreate,
    vehicle: Vehicle,
    test_run: TestRun | None,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[FaultCampaignExecution, bool]:
    existing = await session.scalar(
        select(FaultCampaignExecution).where(
            FaultCampaignExecution.execution_id == command.execution_id
        )
    )
    if existing is not None:
        if not _same_execution_creation(
            existing, campaign, command, vehicle, test_run, actor_user_id
        ):
            raise FaultExecutionConflictError()
        return existing, True
    if campaign.status != FaultCampaignStatus.ACTIVE.value:
        raise FaultCampaignStateError(current_status=campaign.status, requested_status="execute")
    if test_run is not None and test_run.vehicle_id != vehicle.id:
        raise FaultExecutionConflictError()

    created_at = now or datetime.now(UTC)
    snapshot = _campaign_snapshot(campaign, command.test_run_id)
    execution = FaultCampaignExecution(
        execution_id=command.execution_id,
        campaign_id=campaign.id,
        campaign_version=campaign.version,
        campaign_snapshot=snapshot,
        vehicle_id=vehicle.id,
        test_run_id=test_run.id if test_run else None,
        requested_by_user_id=actor_user_id,
        seed=command.seed,
        dry_run=command.dry_run,
        metadata_=command.metadata,
        status=FaultExecutionStatus.QUEUED.value,
        progress_percent=0,
        version=1,
        summary=None,
        started_at=None,
        completed_at=None,
        created_at=created_at,
        updated_at=created_at,
    )
    try:
        async with session.begin_nested():
            session.add(execution)
            await session.flush()
            for step in snapshot["steps"]:
                session.add(
                    FaultStepResult(
                        execution_id=execution.id,
                        step_id=str(step["step_id"]),
                        order=int(step["order"]),
                        domain=str(step["domain"]),
                        action=str(step["action"]),
                        target_id=str(step["target_id"]),
                        required=bool(step["required"]),
                        status=FaultStepStatus.PENDING.value,
                        attempt=0,
                        duration_ms=None,
                        observed_effect=None,
                        evidence_refs=[],
                        version=1,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
            await session.flush()
    except IntegrityError as exc:
        raise FaultExecutionConflictError() from exc

    payload = execution_event_payload(execution, campaign.campaign_id, vehicle.identifier)
    _record_evidence(
        session,
        resource=execution,
        event_type="atep.fault_campaign.execution.requested.v1",
        action="fault_campaign.execution_requested",
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload=payload,
    )
    return execution, False


async def require_execution(
    session: AsyncSession, execution_id: str, *, for_update: bool = False
) -> tuple[FaultCampaignExecution, FaultCampaign, Vehicle]:
    query = (
        select(FaultCampaignExecution, FaultCampaign, Vehicle)
        .join(FaultCampaign, FaultCampaign.id == FaultCampaignExecution.campaign_id)
        .join(Vehicle, Vehicle.id == FaultCampaignExecution.vehicle_id)
        .where(FaultCampaignExecution.execution_id == execution_id)
    )
    if for_update:
        query = query.with_for_update(of=FaultCampaignExecution)
    row = (await session.execute(query)).one_or_none()
    if row is None:
        raise ResourceNotFoundError("fault_execution")
    return row.tuple()


async def list_executions(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: FaultExecutionStatus | None,
    vehicle_identifier: str | None,
) -> tuple[list[tuple[FaultCampaignExecution, FaultCampaign, Vehicle]], int]:
    query = (
        select(FaultCampaignExecution, FaultCampaign, Vehicle)
        .join(FaultCampaign, FaultCampaign.id == FaultCampaignExecution.campaign_id)
        .join(Vehicle, Vehicle.id == FaultCampaignExecution.vehicle_id)
    )
    if status is not None:
        query = query.where(FaultCampaignExecution.status == status.value)
    if vehicle_identifier is not None:
        query = query.where(Vehicle.identifier == vehicle_identifier)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(FaultCampaignExecution.created_at.desc(), FaultCampaignExecution.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [row.tuple() for row in rows.all()], int(total or 0)


async def require_step_result(
    session: AsyncSession,
    *,
    execution: FaultCampaignExecution,
    step_id: str,
    for_update: bool = False,
) -> FaultStepResult:
    query = select(FaultStepResult).where(
        FaultStepResult.execution_id == execution.id,
        FaultStepResult.step_id == step_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.scalar(query)
    if result is None:
        raise ResourceNotFoundError("fault_step_result")
    return result


async def list_step_results(
    session: AsyncSession,
    *,
    execution: FaultCampaignExecution,
    limit: int,
    offset: int,
) -> tuple[list[FaultStepResult], int]:
    query = select(FaultStepResult).where(FaultStepResult.execution_id == execution.id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(FaultStepResult.order, FaultStepResult.id).limit(limit).offset(offset)
    )
    return list(rows), int(total or 0)


async def update_step_result(
    session: AsyncSession,
    *,
    execution: FaultCampaignExecution,
    campaign: FaultCampaign,
    vehicle: Vehicle,
    result: FaultStepResult,
    command: FaultStepResultUpdate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[FaultStepResult, bool]:
    if _same_step_result(result, command):
        return result, True
    if execution.status in {
        FaultExecutionStatus.PASSED.value,
        FaultExecutionStatus.FAILED.value,
        FaultExecutionStatus.CANCELLED.value,
    }:
        raise FaultExecutionStateError(
            current_status=execution.status, requested_status="record_step_result"
        )
    if result.version != command.expected_version:
        raise FaultStepVersionConflictError(current_version=result.version)
    current = FaultStepStatus(result.status)
    if command.status not in STEP_TRANSITIONS[current]:
        raise FaultStepStateError(
            current_status=current.value, requested_status=command.status.value
        )

    changed_at = now or datetime.now(UTC)
    previous_status = result.status
    result.status = command.status.value
    result.attempt = command.attempt
    result.duration_ms = command.duration_ms
    result.observed_effect = command.observed_effect
    result.evidence_refs = command.evidence_refs
    result.version += 1
    result.updated_at = changed_at
    await session.flush()
    await _refresh_execution_aggregate(session, execution, changed_at)

    payload = {
        "execution_id": execution.execution_id,
        "campaign_id": campaign.campaign_id,
        "vehicle_id": vehicle.identifier,
        "step_id": result.step_id,
        "domain": result.domain,
        "action": result.action,
        "target_id": result.target_id,
        "required": result.required,
        "previous_status": previous_status,
        "status": result.status,
        "attempt": result.attempt,
        "duration_ms": result.duration_ms,
        "evidence_count": len(result.evidence_refs),
        "version": result.version,
    }
    _record_evidence(
        session,
        resource=result,
        event_type="atep.fault_campaign.step_recorded.v1",
        action="fault_campaign.step_recorded",
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload=payload,
    )
    return result, False


async def cancel_execution(
    session: AsyncSession,
    *,
    execution: FaultCampaignExecution,
    campaign: FaultCampaign,
    vehicle: Vehicle,
    command: FaultExecutionCancel,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[FaultCampaignExecution, bool]:
    if (
        execution.status == FaultExecutionStatus.CANCELLED.value
        and execution.summary == command.reason
    ):
        return execution, True
    if execution.version != command.expected_version:
        raise FaultExecutionVersionConflictError(current_version=execution.version)
    if execution.status in {
        FaultExecutionStatus.PASSED.value,
        FaultExecutionStatus.FAILED.value,
        FaultExecutionStatus.CANCELLED.value,
    }:
        raise FaultExecutionStateError(
            current_status=execution.status,
            requested_status=FaultExecutionStatus.CANCELLED.value,
        )
    changed_at = now or datetime.now(UTC)
    execution.status = FaultExecutionStatus.CANCELLED.value
    execution.summary = command.reason
    execution.version += 1
    execution.completed_at = changed_at
    execution.updated_at = changed_at
    await session.flush()
    payload = execution_event_payload(execution, campaign.campaign_id, vehicle.identifier)
    _record_evidence(
        session,
        resource=execution,
        event_type="atep.fault_campaign.execution.cancelled.v1",
        action="fault_campaign.execution_cancelled",
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload=payload,
    )
    return execution, False


async def _refresh_execution_aggregate(
    session: AsyncSession, execution: FaultCampaignExecution, changed_at: datetime
) -> None:
    results = list(
        await session.scalars(
            select(FaultStepResult).where(FaultStepResult.execution_id == execution.id)
        )
    )
    complete = sum(item.status in TERMINAL_STEP_STATUSES for item in results)
    total = len(results)
    execution.progress_percent = (
        100 if total and complete == total else min(99, complete * 100 // total)
    )
    if execution.status == FaultExecutionStatus.QUEUED.value:
        execution.status = FaultExecutionStatus.RUNNING.value
        execution.started_at = changed_at
    if total and complete == total:
        failed = any(
            item.required
            and item.status in {FaultStepStatus.FAILED.value, FaultStepStatus.SKIPPED.value}
            for item in results
        )
        execution.status = (
            FaultExecutionStatus.FAILED.value if failed else FaultExecutionStatus.PASSED.value
        )
        execution.completed_at = changed_at
        execution.summary = f"{complete} of {total} fault steps reached a terminal state"
    execution.version += 1
    execution.updated_at = changed_at
    await session.flush()


def campaign_response(campaign: FaultCampaign) -> FaultCampaignResponse:
    return FaultCampaignResponse(
        id=campaign.id,
        campaign_id=campaign.campaign_id,
        created_by_user_id=campaign.created_by_user_id,
        name=campaign.name,
        description=campaign.description,
        blast_radius=campaign.blast_radius,
        steps=campaign.steps,
        tags=campaign.tags,
        status=campaign.status,
        version=campaign.version,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


def execution_response(
    execution: FaultCampaignExecution, campaign: FaultCampaign, vehicle: Vehicle
) -> FaultExecutionResponse:
    return FaultExecutionResponse(
        id=execution.id,
        execution_id=execution.execution_id,
        campaign_id=campaign.campaign_id,
        campaign_version=execution.campaign_version,
        campaign_snapshot=execution.campaign_snapshot,
        vehicle_id=vehicle.identifier,
        test_run_id=execution.campaign_snapshot.get("test_run_id"),
        requested_by_user_id=execution.requested_by_user_id,
        seed=execution.seed,
        dry_run=execution.dry_run,
        metadata=execution.metadata_,
        status=execution.status,
        progress_percent=execution.progress_percent,
        version=execution.version,
        summary=execution.summary,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
    )


def step_result_response(result: FaultStepResult, execution_id: str) -> FaultStepResultResponse:
    return FaultStepResultResponse(
        id=result.id,
        execution_id=execution_id,
        step_id=result.step_id,
        order=result.order,
        domain=result.domain,
        action=result.action,
        target_id=result.target_id,
        required=result.required,
        status=result.status,
        attempt=result.attempt,
        duration_ms=result.duration_ms,
        observed_effect=result.observed_effect,
        evidence_refs=result.evidence_refs,
        version=result.version,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


def campaign_event_payload(campaign: FaultCampaign) -> dict[str, object]:
    domains = sorted({str(item["domain"]) for item in campaign.steps})
    budget_ms = sum(
        int(item["duration_ms"]) + int(item["recovery"]["timeout_ms"]) for item in campaign.steps
    )
    return {
        "campaign_id": campaign.campaign_id,
        "created_by_user_id": str(campaign.created_by_user_id),
        "name": campaign.name,
        "blast_radius": campaign.blast_radius,
        "domains": domains,
        "step_count": len(campaign.steps),
        "budget_ms": budget_ms,
        "status": campaign.status,
        "version": campaign.version,
        "snapshot_fingerprint": _fingerprint(_campaign_snapshot(campaign, None)),
    }


def execution_event_payload(
    execution: FaultCampaignExecution, campaign_id: str, vehicle_identifier: str
) -> dict[str, object]:
    return {
        "execution_id": execution.execution_id,
        "campaign_id": campaign_id,
        "campaign_version": execution.campaign_version,
        "campaign_fingerprint": _fingerprint(execution.campaign_snapshot),
        "vehicle_id": vehicle_identifier,
        "test_run_id": execution.campaign_snapshot.get("test_run_id"),
        "requested_by_user_id": str(execution.requested_by_user_id),
        "seed": execution.seed,
        "dry_run": execution.dry_run,
        "step_count": len(execution.campaign_snapshot.get("steps", [])),
        "status": execution.status,
        "progress_percent": execution.progress_percent,
        "version": execution.version,
        "summary": execution.summary,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
    }


def _campaign_snapshot(campaign: FaultCampaign, test_run_id: str | None) -> dict[str, Any]:
    return {
        "campaign_id": campaign.campaign_id,
        "name": campaign.name,
        "blast_radius": campaign.blast_radius,
        "steps": deepcopy(campaign.steps),
        "tags": deepcopy(campaign.tags),
        "test_run_id": test_run_id,
    }


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _same_campaign_creation(
    campaign: FaultCampaign, command: FaultCampaignCreate, actor_user_id: UUID
) -> bool:
    return (
        campaign.created_by_user_id == actor_user_id
        and campaign.name == command.name
        and campaign.description == command.description
        and campaign.blast_radius == command.blast_radius.value
        and campaign.steps
        == [item.model_dump(mode="json") for item in sorted(command.steps, key=lambda x: x.order)]
        and campaign.tags == command.tags
    )


def _same_execution_creation(
    execution: FaultCampaignExecution,
    campaign: FaultCampaign,
    command: FaultExecutionCreate,
    vehicle: Vehicle,
    test_run: TestRun | None,
    actor_user_id: UUID,
) -> bool:
    return (
        execution.campaign_id == campaign.id
        and execution.vehicle_id == vehicle.id
        and execution.test_run_id == (test_run.id if test_run else None)
        and execution.requested_by_user_id == actor_user_id
        and execution.seed == command.seed
        and execution.dry_run == command.dry_run
        and execution.metadata_ == command.metadata
    )


def _same_step_result(result: FaultStepResult, command: FaultStepResultUpdate) -> bool:
    return (
        result.status == command.status.value
        and result.attempt == command.attempt
        and result.duration_ms == command.duration_ms
        and result.observed_effect == command.observed_effect
        and result.evidence_refs == command.evidence_refs
    )


async def _persist(session: AsyncSession, resource: object, error: Exception) -> None:
    try:
        async with session.begin_nested():
            session.add(resource)
            await session.flush()
    except IntegrityError as exc:
        raise error from exc


def _record_evidence(
    session: AsyncSession,
    *,
    resource: FaultCampaign | FaultCampaignExecution | FaultStepResult,
    event_type: str,
    action: str,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    payload: dict[str, object],
) -> None:
    aggregate_type = (
        "fault_campaign"
        if isinstance(resource, FaultCampaign)
        else "fault_campaign_execution"
        if isinstance(resource, FaultCampaignExecution)
        else "fault_step_result"
    )
    enqueue_event(
        session,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=resource.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=aggregate_type,
        resource_id=resource.id,
        correlation_id=correlation_id,
        details=payload,
    )
