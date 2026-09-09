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
    MutantResultStateError,
    MutantResultVersionConflictError,
    MutationCampaignConflictError,
    MutationCampaignStateError,
    MutationCampaignVersionConflictError,
    MutationExecutionConflictError,
    RequirementCoverageConflictError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event
from atep.mutation_analysis.models import (
    MutantResult,
    MutationCampaign,
    MutationExecution,
    RequirementCoverage,
)
from atep.mutation_analysis.schemas import (
    CampaignStatus,
    CampaignStatusUpdate,
    CoverageStatus,
    ExecutionStatus,
    MutantResultResponse,
    MutantResultUpdate,
    MutantStatus,
    MutationCampaignCreate,
    MutationCampaignResponse,
    MutationExecutionCreate,
    MutationExecutionResponse,
    RequirementCoverageResponse,
    RequirementCoverageUpsert,
    coverage_status,
)
from atep.test_catalog.models import TestDefinition, TestSuite
from atep.test_catalog.schemas import CatalogStatus
from atep.test_runs.models import TestRun
from atep.vehicles.models import Vehicle

CAMPAIGN_TRANSITIONS = {
    CampaignStatus.DRAFT: {CampaignStatus.ACTIVE},
    CampaignStatus.ACTIVE: {CampaignStatus.ARCHIVED},
    CampaignStatus.ARCHIVED: set(),
}
RESULT_TRANSITIONS = {
    MutantStatus.PENDING: {MutantStatus.RUNNING, MutantStatus.SKIPPED},
    MutantStatus.RUNNING: {
        MutantStatus.KILLED,
        MutantStatus.SURVIVED,
        MutantStatus.ERROR,
        MutantStatus.SKIPPED,
    },
    MutantStatus.KILLED: set(),
    MutantStatus.SURVIVED: set(),
    MutantStatus.ERROR: set(),
    MutantStatus.SKIPPED: set(),
}
TERMINAL_RESULTS = {
    MutantStatus.KILLED.value,
    MutantStatus.SURVIVED.value,
    MutantStatus.ERROR.value,
    MutantStatus.SKIPPED.value,
}


async def create_campaign(
    session: AsyncSession,
    *,
    command: MutationCampaignCreate,
    suite: TestSuite,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[MutationCampaign, bool]:
    existing = await session.scalar(
        select(MutationCampaign).where(MutationCampaign.campaign_id == command.campaign_id)
    )
    if existing is not None:
        if not _same_campaign(existing, command, suite, actor_user_id):
            raise MutationCampaignConflictError()
        return existing, True
    if suite.status != CatalogStatus.ACTIVE.value:
        raise MutationCampaignStateError(current_status=suite.status, requested_status="compose")

    created_at = now or datetime.now(UTC)
    campaign = MutationCampaign(
        campaign_id=command.campaign_id,
        created_by_user_id=actor_user_id,
        catalog_suite_id=suite.id,
        suite_version=suite.version,
        suite_snapshot=_suite_snapshot(suite),
        name=command.name,
        description=command.description,
        mutants=[
            item.model_dump(mode="json") for item in sorted(command.mutants, key=lambda x: x.order)
        ],
        tags=command.tags,
        status=CampaignStatus.DRAFT.value,
        version=1,
        created_at=created_at,
        updated_at=created_at,
    )
    await _persist(session, campaign, MutationCampaignConflictError())
    _record_evidence(
        session,
        resource=campaign,
        event_type="atep.mutation_campaign.created.v1",
        action="mutation_campaign.created",
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload=campaign_evidence(campaign),
    )
    return campaign, False


async def require_campaign(
    session: AsyncSession, campaign_id: str, *, for_update: bool = False
) -> tuple[MutationCampaign, TestSuite]:
    query = (
        select(MutationCampaign, TestSuite)
        .join(TestSuite, TestSuite.id == MutationCampaign.catalog_suite_id)
        .where(MutationCampaign.campaign_id == campaign_id)
    )
    if for_update:
        query = query.with_for_update(of=MutationCampaign)
    row = (await session.execute(query)).one_or_none()
    if row is None:
        raise ResourceNotFoundError("mutation_campaign")
    return row.tuple()


async def list_campaigns(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: CampaignStatus | None,
) -> tuple[list[tuple[MutationCampaign, TestSuite]], int]:
    query = select(MutationCampaign, TestSuite).join(
        TestSuite, TestSuite.id == MutationCampaign.catalog_suite_id
    )
    if status is not None:
        query = query.where(MutationCampaign.status == status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(MutationCampaign.campaign_id).limit(limit).offset(offset)
    )
    return [row.tuple() for row in rows.all()], int(total or 0)


async def update_campaign_status(
    session: AsyncSession,
    *,
    campaign: MutationCampaign,
    command: CampaignStatusUpdate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[MutationCampaign, bool]:
    if campaign.status == command.status.value:
        return campaign, True
    if campaign.version != command.expected_version:
        raise MutationCampaignVersionConflictError(current_version=campaign.version)
    current = CampaignStatus(campaign.status)
    if command.status not in CAMPAIGN_TRANSITIONS[current]:
        raise MutationCampaignStateError(
            current_status=current.value, requested_status=command.status.value
        )
    previous = campaign.status
    campaign.status = command.status.value
    campaign.version += 1
    await session.flush()
    await session.refresh(campaign, attribute_names=["updated_at"])
    _record_evidence(
        session,
        resource=campaign,
        event_type="atep.mutation_campaign.status_changed.v1",
        action="mutation_campaign.status_changed",
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload={**campaign_evidence(campaign), "previous_status": previous},
    )
    return campaign, False


async def create_execution(
    session: AsyncSession,
    *,
    campaign: MutationCampaign,
    command: MutationExecutionCreate,
    vehicle: Vehicle,
    test_run: TestRun | None,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[MutationExecution, bool]:
    existing = await session.scalar(
        select(MutationExecution).where(MutationExecution.execution_id == command.execution_id)
    )
    if existing is not None:
        if not _same_execution(existing, campaign, vehicle, test_run, actor_user_id):
            raise MutationExecutionConflictError()
        return existing, True
    if campaign.status != CampaignStatus.ACTIVE.value:
        raise MutationCampaignStateError(current_status=campaign.status, requested_status="execute")
    if test_run is not None and test_run.vehicle_id != vehicle.id:
        raise MutationExecutionConflictError()

    created_at = now or datetime.now(UTC)
    snapshot = _campaign_snapshot(campaign, command.test_run_id)
    execution = MutationExecution(
        execution_id=command.execution_id,
        campaign_id=campaign.id,
        campaign_version=campaign.version,
        campaign_snapshot=snapshot,
        vehicle_id=vehicle.id,
        test_run_id=test_run.id if test_run else None,
        requested_by_user_id=actor_user_id,
        status=ExecutionStatus.QUEUED.value,
        total_mutants=len(campaign.mutants),
        completed_mutants=0,
        killed_mutants=0,
        survived_mutants=0,
        mutation_score=None,
        version=1,
        started_at=None,
        completed_at=None,
        created_at=created_at,
        updated_at=created_at,
    )
    try:
        async with session.begin_nested():
            session.add(execution)
            await session.flush()
            for mutant in snapshot["mutants"]:
                session.add(
                    MutantResult(
                        execution_id=execution.id,
                        mutant_id=str(mutant["mutant_id"]),
                        order=int(mutant["order"]),
                        operator=str(mutant["operator"]),
                        target=str(mutant["target"]),
                        required=bool(mutant["required"]),
                        status=MutantStatus.PENDING.value,
                        duration_ms=None,
                        detected_by=[],
                        evidence_refs=[],
                        version=1,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
            await session.flush()
    except IntegrityError as exc:
        raise MutationExecutionConflictError() from exc
    _record_evidence(
        session,
        resource=execution,
        event_type="atep.mutation_execution.created.v1",
        action="mutation_execution.created",
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload=execution_evidence(execution, campaign.campaign_id, vehicle.identifier),
    )
    return execution, False


async def require_execution(
    session: AsyncSession, execution_id: str, *, for_update: bool = False
) -> tuple[MutationExecution, MutationCampaign, Vehicle]:
    query = (
        select(MutationExecution, MutationCampaign, Vehicle)
        .join(MutationCampaign, MutationCampaign.id == MutationExecution.campaign_id)
        .join(Vehicle, Vehicle.id == MutationExecution.vehicle_id)
        .where(MutationExecution.execution_id == execution_id)
    )
    if for_update:
        query = query.with_for_update(of=MutationExecution)
    row = (await session.execute(query)).one_or_none()
    if row is None:
        raise ResourceNotFoundError("mutation_execution")
    return row.tuple()


async def list_executions(
    session: AsyncSession, *, limit: int, offset: int, status: ExecutionStatus | None
) -> tuple[list[tuple[MutationExecution, MutationCampaign, Vehicle]], int]:
    query = (
        select(MutationExecution, MutationCampaign, Vehicle)
        .join(MutationCampaign, MutationCampaign.id == MutationExecution.campaign_id)
        .join(Vehicle, Vehicle.id == MutationExecution.vehicle_id)
    )
    if status is not None:
        query = query.where(MutationExecution.status == status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(MutationExecution.created_at.desc()).limit(limit).offset(offset)
    )
    return [row.tuple() for row in rows.all()], int(total or 0)


async def require_result(
    session: AsyncSession,
    *,
    execution: MutationExecution,
    mutant_id: str,
    for_update: bool = False,
) -> MutantResult:
    query = select(MutantResult).where(
        MutantResult.execution_id == execution.id, MutantResult.mutant_id == mutant_id
    )
    if for_update:
        query = query.with_for_update()
    result = await session.scalar(query)
    if result is None:
        raise ResourceNotFoundError("mutant_result")
    return result


async def list_results(
    session: AsyncSession, *, execution: MutationExecution, limit: int, offset: int
) -> tuple[list[MutantResult], int]:
    query = select(MutantResult).where(MutantResult.execution_id == execution.id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(query.order_by(MutantResult.order).limit(limit).offset(offset))
    return list(rows), int(total or 0)


async def update_result(
    session: AsyncSession,
    *,
    execution: MutationExecution,
    campaign: MutationCampaign,
    vehicle: Vehicle,
    result: MutantResult,
    command: MutantResultUpdate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[MutantResult, bool]:
    if _same_result(result, command):
        return result, True
    if execution.status in {
        ExecutionStatus.PASSED.value,
        ExecutionStatus.FAILED.value,
        ExecutionStatus.CANCELLED.value,
    }:
        raise MutantResultStateError(
            current_status=execution.status, requested_status=command.status.value
        )
    if result.version != command.expected_version:
        raise MutantResultVersionConflictError(current_version=result.version)
    current = MutantStatus(result.status)
    if command.status not in RESULT_TRANSITIONS[current]:
        raise MutantResultStateError(
            current_status=current.value, requested_status=command.status.value
        )
    changed_at = now or datetime.now(UTC)
    previous = result.status
    result.status = command.status.value
    result.duration_ms = command.duration_ms
    result.detected_by = command.detected_by
    result.evidence_refs = command.evidence_refs
    result.version += 1
    result.updated_at = changed_at
    await session.flush()
    await _refresh_execution(session, execution, changed_at)
    payload = {
        "execution_id": execution.execution_id,
        "campaign_id": campaign.campaign_id,
        "vehicle_id": vehicle.identifier,
        "mutant_id": result.mutant_id,
        "operator": result.operator,
        "required": result.required,
        "previous_status": previous,
        "status": result.status,
        "duration_ms": result.duration_ms,
        "detected_by_count": len(result.detected_by),
        "evidence_count": len(result.evidence_refs),
        "version": result.version,
    }
    _record_evidence(
        session,
        resource=result,
        event_type="atep.mutant_result.recorded.v1",
        action="mutant_result.recorded",
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload=payload,
    )
    return result, False


async def upsert_requirement_coverage(
    session: AsyncSession,
    *,
    requirement_id: str,
    command: RequirementCoverageUpsert,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[RequirementCoverage, bool]:
    definitions = list(
        await session.scalars(
            select(TestDefinition).where(TestDefinition.definition_id.in_(command.definition_ids))
        )
    )
    if {item.definition_id for item in definitions} != set(command.definition_ids):
        raise ResourceNotFoundError("test_definition")
    existing = await session.scalar(
        select(RequirementCoverage)
        .where(RequirementCoverage.requirement_id == requirement_id)
        .with_for_update()
    )
    desired_status = coverage_status(command.definition_ids, command.evidence_refs).value
    if existing is not None and _same_coverage(existing, command, desired_status):
        return existing, True
    changed_at = now or datetime.now(UTC)
    if existing is None:
        if command.expected_version is not None:
            raise RequirementCoverageConflictError()
        item = RequirementCoverage(
            requirement_id=requirement_id,
            managed_by_user_id=actor_user_id,
            title=command.title.strip(),
            criticality=command.criticality.value,
            definition_ids=command.definition_ids,
            evidence_refs=command.evidence_refs,
            status=desired_status,
            version=1,
            created_at=changed_at,
            updated_at=changed_at,
        )
        await _persist(session, item, RequirementCoverageConflictError())
        action = "requirement_coverage.created"
        event_type = "atep.requirement_coverage.created.v1"
    else:
        if existing.version != command.expected_version:
            raise RequirementCoverageConflictError(current_version=existing.version)
        existing.managed_by_user_id = actor_user_id
        existing.title = command.title.strip()
        existing.criticality = command.criticality.value
        existing.definition_ids = command.definition_ids
        existing.evidence_refs = command.evidence_refs
        existing.status = desired_status
        existing.version += 1
        existing.updated_at = changed_at
        await session.flush()
        item = existing
        action = "requirement_coverage.updated"
        event_type = "atep.requirement_coverage.updated.v1"
    _record_evidence(
        session,
        resource=item,
        event_type=event_type,
        action=action,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload=coverage_evidence(item),
    )
    return item, False


async def require_coverage(session: AsyncSession, requirement_id: str) -> RequirementCoverage:
    item = await session.scalar(
        select(RequirementCoverage).where(RequirementCoverage.requirement_id == requirement_id)
    )
    if item is None:
        raise ResourceNotFoundError("requirement_coverage")
    return item


async def list_coverage(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: CoverageStatus | None,
) -> tuple[list[RequirementCoverage], int, dict[str, int]]:
    base = select(RequirementCoverage)
    query = base
    if status is not None:
        query = query.where(RequirementCoverage.status == status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(RequirementCoverage.requirement_id).limit(limit).offset(offset)
    )
    counts = {
        value.value: int(
            await session.scalar(
                select(func.count()).where(RequirementCoverage.status == value.value)
            )
            or 0
        )
        for value in CoverageStatus
    }
    return list(rows), int(total or 0), counts


async def _refresh_execution(
    session: AsyncSession, execution: MutationExecution, changed_at: datetime
) -> None:
    results = list(
        await session.scalars(select(MutantResult).where(MutantResult.execution_id == execution.id))
    )
    terminal = [item for item in results if item.status in TERMINAL_RESULTS]
    execution.completed_mutants = len(terminal)
    execution.killed_mutants = sum(item.status == MutantStatus.KILLED.value for item in terminal)
    execution.survived_mutants = sum(
        item.status == MutantStatus.SURVIVED.value for item in terminal
    )
    if execution.status == ExecutionStatus.QUEUED.value:
        execution.status = ExecutionStatus.RUNNING.value
        execution.started_at = changed_at
    if len(terminal) == len(results):
        denominator = execution.killed_mutants + execution.survived_mutants
        execution.mutation_score = (
            round(execution.killed_mutants / denominator, 6) if denominator else None
        )
        failed = any(
            item.required
            and item.status
            in {MutantStatus.SURVIVED.value, MutantStatus.ERROR.value, MutantStatus.SKIPPED.value}
            for item in results
        )
        execution.status = ExecutionStatus.FAILED.value if failed else ExecutionStatus.PASSED.value
        execution.completed_at = changed_at
    execution.version += 1
    execution.updated_at = changed_at
    await session.flush()


def campaign_response(campaign: MutationCampaign, suite: TestSuite) -> MutationCampaignResponse:
    return MutationCampaignResponse(
        id=campaign.id,
        campaign_id=campaign.campaign_id,
        created_by_user_id=campaign.created_by_user_id,
        catalog_suite_id=suite.suite_id,
        suite_version=campaign.suite_version,
        suite_snapshot=campaign.suite_snapshot,
        name=campaign.name,
        description=campaign.description,
        mutants=campaign.mutants,
        tags=campaign.tags,
        status=campaign.status,
        version=campaign.version,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


def execution_response(
    execution: MutationExecution, campaign: MutationCampaign, vehicle: Vehicle
) -> MutationExecutionResponse:
    return MutationExecutionResponse(
        id=execution.id,
        execution_id=execution.execution_id,
        campaign_id=campaign.campaign_id,
        campaign_version=execution.campaign_version,
        campaign_snapshot=execution.campaign_snapshot,
        vehicle_id=vehicle.identifier,
        test_run_id=execution.campaign_snapshot.get("test_run_id"),
        requested_by_user_id=execution.requested_by_user_id,
        status=execution.status,
        total_mutants=execution.total_mutants,
        completed_mutants=execution.completed_mutants,
        killed_mutants=execution.killed_mutants,
        survived_mutants=execution.survived_mutants,
        mutation_score=execution.mutation_score,
        version=execution.version,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
    )


def result_response(result: MutantResult, execution_id: str) -> MutantResultResponse:
    return MutantResultResponse(
        id=result.id,
        execution_id=execution_id,
        mutant_id=result.mutant_id,
        order=result.order,
        operator=result.operator,
        target=result.target,
        required=result.required,
        status=result.status,
        duration_ms=result.duration_ms,
        detected_by=result.detected_by,
        evidence_refs=result.evidence_refs,
        version=result.version,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


def coverage_response(item: RequirementCoverage) -> RequirementCoverageResponse:
    return RequirementCoverageResponse(
        id=item.id,
        requirement_id=item.requirement_id,
        managed_by_user_id=item.managed_by_user_id,
        title=item.title,
        criticality=item.criticality,
        definition_ids=item.definition_ids,
        evidence_refs=item.evidence_refs,
        status=item.status,
        version=item.version,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def campaign_evidence(campaign: MutationCampaign) -> dict[str, object]:
    return {
        "campaign_id": campaign.campaign_id,
        "suite_version": campaign.suite_version,
        "suite_fingerprint": _fingerprint(campaign.suite_snapshot),
        "mutant_count": len(campaign.mutants),
        "operators": sorted({str(item["operator"]) for item in campaign.mutants}),
        "status": campaign.status,
        "version": campaign.version,
    }


def execution_evidence(
    execution: MutationExecution, campaign_id: str, vehicle_id: str
) -> dict[str, object]:
    return {
        "execution_id": execution.execution_id,
        "campaign_id": campaign_id,
        "campaign_version": execution.campaign_version,
        "campaign_fingerprint": _fingerprint(execution.campaign_snapshot),
        "vehicle_id": vehicle_id,
        "test_run_id": execution.campaign_snapshot.get("test_run_id"),
        "total_mutants": execution.total_mutants,
        "completed_mutants": execution.completed_mutants,
        "killed_mutants": execution.killed_mutants,
        "survived_mutants": execution.survived_mutants,
        "mutation_score": execution.mutation_score,
        "status": execution.status,
        "version": execution.version,
    }


def coverage_evidence(item: RequirementCoverage) -> dict[str, object]:
    return {
        "requirement_id": item.requirement_id,
        "criticality": item.criticality,
        "definition_count": len(item.definition_ids),
        "evidence_count": len(item.evidence_refs),
        "status": item.status,
        "version": item.version,
    }


def _suite_snapshot(suite: TestSuite) -> dict[str, object]:
    return {
        "suite_id": suite.suite_id,
        "name": suite.name,
        "suite_type": suite.suite_type,
        "version": suite.version,
        "composition": deepcopy(suite.composition),
        "tags": deepcopy(suite.tags),
    }


def _campaign_snapshot(campaign: MutationCampaign, test_run_id: str | None) -> dict[str, Any]:
    return {
        "campaign_id": campaign.campaign_id,
        "name": campaign.name,
        "suite": deepcopy(campaign.suite_snapshot),
        "mutants": deepcopy(campaign.mutants),
        "tags": deepcopy(campaign.tags),
        "test_run_id": test_run_id,
    }


def _fingerprint(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _same_campaign(
    item: MutationCampaign,
    command: MutationCampaignCreate,
    suite: TestSuite,
    actor_user_id: UUID,
) -> bool:
    return (
        item.created_by_user_id == actor_user_id
        and item.catalog_suite_id == suite.id
        and item.name == command.name
        and item.description == command.description
        and item.mutants
        == [
            value.model_dump(mode="json")
            for value in sorted(command.mutants, key=lambda x: x.order)
        ]
        and item.tags == command.tags
    )


def _same_execution(
    item: MutationExecution,
    campaign: MutationCampaign,
    vehicle: Vehicle,
    test_run: TestRun | None,
    actor_user_id: UUID,
) -> bool:
    return (
        item.campaign_id == campaign.id
        and item.vehicle_id == vehicle.id
        and item.test_run_id == (test_run.id if test_run else None)
        and item.requested_by_user_id == actor_user_id
    )


def _same_result(item: MutantResult, command: MutantResultUpdate) -> bool:
    return (
        item.status == command.status.value
        and item.duration_ms == command.duration_ms
        and item.detected_by == command.detected_by
        and item.evidence_refs == command.evidence_refs
    )


def _same_coverage(
    item: RequirementCoverage, command: RequirementCoverageUpsert, desired_status: str
) -> bool:
    return (
        item.title == command.title.strip()
        and item.criticality == command.criticality.value
        and item.definition_ids == command.definition_ids
        and item.evidence_refs == command.evidence_refs
        and item.status == desired_status
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
    resource: MutationCampaign | MutationExecution | MutantResult | RequirementCoverage,
    event_type: str,
    action: str,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    payload: dict[str, object],
) -> None:
    aggregate_type = (
        "mutation_campaign"
        if isinstance(resource, MutationCampaign)
        else "mutation_execution"
        if isinstance(resource, MutationExecution)
        else "mutant_result"
        if isinstance(resource, MutantResult)
        else "requirement_coverage"
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
