from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    ResourceNotFoundError,
    TestCatalogStateError,
    TestCatalogVersionConflictError,
    TestDefinitionConflictError,
    TestSuiteConflictError,
)
from atep.events.outbox import enqueue_event
from atep.test_catalog.models import TestDefinition, TestSuite
from atep.test_catalog.schemas import (
    CatalogStatus,
    CatalogStatusUpdate,
    TestDefinitionCreate,
    TestDefinitionResponse,
    TestSuiteCreate,
    TestSuiteResponse,
)

ALLOWED_TRANSITIONS = {
    CatalogStatus.DRAFT: {CatalogStatus.ACTIVE},
    CatalogStatus.ACTIVE: {CatalogStatus.ARCHIVED},
    CatalogStatus.ARCHIVED: set(),
}


async def create_definition(
    session: AsyncSession,
    *,
    command: TestDefinitionCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[TestDefinition, bool]:
    existing = await session.scalar(
        select(TestDefinition).where(TestDefinition.definition_id == command.definition_id)
    )
    requested = _definition_command_payload(command, actor_user_id)
    if existing is not None:
        if not _matches_creation(
            definition_payload(existing), requested, ignored={"status", "version"}
        ):
            raise TestDefinitionConflictError()
        return existing, True
    definition = TestDefinition(**requested)
    await _persist(session, definition, TestDefinitionConflictError())
    _record_created(
        session,
        resource=definition,
        aggregate_type="test_definition",
        event_type="atep.test_definition.created.v1",
        action="test_definition.created",
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload=definition_evidence_payload(definition),
    )
    return definition, False


async def create_suite(
    session: AsyncSession,
    *,
    command: TestSuiteCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[TestSuite, bool]:
    existing = await session.scalar(select(TestSuite).where(TestSuite.suite_id == command.suite_id))
    if existing is not None:
        if not _suite_creation_matches(existing, command, actor_user_id):
            raise TestSuiteConflictError()
        return existing, True
    payload = await _suite_command_payload(session, command, actor_user_id)
    suite = TestSuite(**payload)
    await _persist(session, suite, TestSuiteConflictError())
    _record_created(
        session,
        resource=suite,
        aggregate_type="test_suite",
        event_type="atep.test_suite.created.v1",
        action="test_suite.created",
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        payload=suite_evidence_payload(suite),
    )
    return suite, False


async def require_definition(
    session: AsyncSession, definition_id: str, *, for_update: bool = False
) -> TestDefinition:
    query = select(TestDefinition).where(TestDefinition.definition_id == definition_id)
    if for_update:
        query = query.with_for_update()
    result = await session.scalar(query)
    if result is None:
        raise ResourceNotFoundError("test_definition")
    return result


async def require_suite(
    session: AsyncSession, suite_id: str, *, for_update: bool = False
) -> TestSuite:
    query = select(TestSuite).where(TestSuite.suite_id == suite_id)
    if for_update:
        query = query.with_for_update()
    result = await session.scalar(query)
    if result is None:
        raise ResourceNotFoundError("test_suite")
    return result


async def list_definitions(
    session: AsyncSession, *, limit: int, offset: int, status: CatalogStatus | None
) -> tuple[list[TestDefinition], int]:
    query = select(TestDefinition)
    if status is not None:
        query = query.where(TestDefinition.status == status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(TestDefinition.definition_id).limit(limit).offset(offset)
    )
    return list(rows), int(total or 0)


async def list_suites(
    session: AsyncSession, *, limit: int, offset: int, status: CatalogStatus | None
) -> tuple[list[TestSuite], int]:
    query = select(TestSuite)
    if status is not None:
        query = query.where(TestSuite.status == status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(query.order_by(TestSuite.suite_id).limit(limit).offset(offset))
    return list(rows), int(total or 0)


async def update_status(
    session: AsyncSession,
    *,
    resource: TestDefinition | TestSuite,
    command: CatalogStatusUpdate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[TestDefinition | TestSuite, bool]:
    if resource.status == command.status.value:
        return resource, True
    if resource.version != command.expected_version:
        raise TestCatalogVersionConflictError(current_version=resource.version)
    current = CatalogStatus(resource.status)
    if command.status not in ALLOWED_TRANSITIONS[current]:
        raise TestCatalogStateError(
            current_status=current.value, requested_status=command.status.value
        )
    previous = resource.status
    resource.status = command.status.value
    resource.version += 1
    await session.flush()
    await session.refresh(resource, attribute_names=["updated_at"])
    kind = "test_definition" if isinstance(resource, TestDefinition) else "test_suite"
    payload: dict[str, object] = (
        definition_evidence_payload(resource)
        if isinstance(resource, TestDefinition)
        else suite_evidence_payload(resource)
    )
    evidence = {**payload, "previous_status": previous}
    enqueue_event(
        session,
        event_type=f"atep.{kind}.status_changed.v1",
        aggregate_type=kind,
        aggregate_id=resource.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action=f"{kind}.status_changed",
        resource_type=kind,
        resource_id=resource.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return resource, False


def definition_response(item: TestDefinition) -> TestDefinitionResponse:
    return TestDefinitionResponse(
        **definition_payload(item), id=item.id, updated_at=item.updated_at
    )


def suite_response(item: TestSuite) -> TestSuiteResponse:
    payload = suite_payload(item)
    payload["cases"] = payload.pop("composition")
    return TestSuiteResponse(**payload, id=item.id, updated_at=item.updated_at)


def definition_payload(item: TestDefinition) -> dict[str, object]:
    return {
        "definition_id": item.definition_id,
        "created_by_user_id": item.created_by_user_id,
        "name": item.name,
        "description": item.description,
        "domain": item.domain,
        "level": item.level,
        "automation_mode": item.automation_mode,
        "timeout_seconds": item.timeout_seconds,
        "tags": item.tags,
        "preconditions": item.preconditions,
        "steps": item.steps,
        "status": item.status,
        "version": item.version,
        "created_at": item.created_at,
    }


def suite_payload(item: TestSuite) -> dict[str, object]:
    return {
        "suite_id": item.suite_id,
        "created_by_user_id": item.created_by_user_id,
        "name": item.name,
        "description": item.description,
        "suite_type": item.suite_type,
        "composition": item.composition,
        "tags": item.tags,
        "status": item.status,
        "version": item.version,
        "created_at": item.created_at,
    }


def definition_evidence_payload(item: TestDefinition) -> dict[str, object]:
    return {
        "definition_id": item.definition_id,
        "created_by_user_id": str(item.created_by_user_id),
        "name": item.name,
        "domain": item.domain,
        "level": item.level,
        "automation_mode": item.automation_mode,
        "status": item.status,
        "version": item.version,
        "step_count": len(item.steps),
    }


def suite_evidence_payload(item: TestSuite) -> dict[str, object]:
    return {
        "suite_id": item.suite_id,
        "created_by_user_id": str(item.created_by_user_id),
        "name": item.name,
        "suite_type": item.suite_type,
        "status": item.status,
        "version": item.version,
        "case_count": len(item.composition),
    }


def _definition_command_payload(
    command: TestDefinitionCreate, actor_user_id: UUID
) -> dict[str, object]:
    return {
        "definition_id": command.definition_id,
        "created_by_user_id": actor_user_id,
        "name": command.name,
        "description": command.description,
        "domain": command.domain.value,
        "level": command.level.value,
        "automation_mode": command.automation_mode.value,
        "timeout_seconds": command.timeout_seconds,
        "tags": command.tags,
        "preconditions": command.preconditions,
        "steps": [item.model_dump(mode="json") for item in command.steps],
        "status": CatalogStatus.DRAFT.value,
        "version": 1,
    }


async def _suite_command_payload(
    session: AsyncSession, command: TestSuiteCreate, actor_user_id: UUID
) -> dict[str, object]:
    identifiers = [item.definition_id for item in command.cases]
    definitions = list(
        await session.scalars(
            select(TestDefinition).where(TestDefinition.definition_id.in_(identifiers))
        )
    )
    by_id = {item.definition_id: item for item in definitions}
    if set(by_id) != set(identifiers):
        raise ResourceNotFoundError("test_definition")
    if any(item.status != CatalogStatus.ACTIVE.value for item in definitions):
        raise TestCatalogStateError(current_status="draft_or_archived", requested_status="compose")
    composition = [
        {
            **case.model_dump(mode="json"),
            "definition_version": by_id[case.definition_id].version,
            "name": by_id[case.definition_id].name,
        }
        for case in sorted(command.cases, key=lambda item: item.order)
    ]
    return {
        "suite_id": command.suite_id,
        "created_by_user_id": actor_user_id,
        "name": command.name.strip(),
        "description": command.description.strip(),
        "suite_type": command.suite_type.value,
        "composition": composition,
        "tags": command.tags,
        "status": CatalogStatus.DRAFT.value,
        "version": 1,
    }


async def _persist(session: AsyncSession, resource: object, error: Exception) -> None:
    try:
        async with session.begin_nested():
            session.add(resource)
            await session.flush()
    except IntegrityError as exc:
        raise error from exc


def _record_created(
    session: AsyncSession,
    *,
    resource: TestDefinition | TestSuite,
    aggregate_type: str,
    event_type: str,
    action: str,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    payload: dict[str, object],
) -> None:
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


def _matches_creation(
    persisted: dict[str, object], requested: dict[str, object], *, ignored: set[str]
) -> bool:
    return all(
        persisted.get(key) == value for key, value in requested.items() if key not in ignored
    )


def _suite_creation_matches(
    suite: TestSuite, command: TestSuiteCreate, actor_user_id: UUID
) -> bool:
    cases = [
        {
            "definition_id": item["definition_id"],
            "order": item["order"],
            "required": item["required"],
            "parameter_overrides": item["parameter_overrides"],
        }
        for item in suite.composition
    ]
    return (
        suite.created_by_user_id == actor_user_id
        and suite.name == command.name.strip()
        and suite.description == command.description.strip()
        and suite.suite_type == command.suite_type.value
        and suite.tags == command.tags
        and cases
        == [item.model_dump(mode="json") for item in sorted(command.cases, key=lambda x: x.order)]
    )
