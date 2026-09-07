import json
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import (
    ResourceNotFoundError,
)
from atep.core.errors import (
    TestCatalogStateError as CatalogStateError,
)
from atep.core.errors import (
    TestCatalogVersionConflictError as CatalogVersionConflictError,
)
from atep.core.errors import (
    TestDefinitionConflictError as DefinitionConflictError,
)
from atep.events.models import OutboxEvent
from atep.test_catalog.models import TestDefinition as DefinitionRecord
from atep.test_catalog.models import TestSuite as SuiteRecord
from atep.test_catalog.schemas import (
    CatalogStatusUpdate,
)
from atep.test_catalog.schemas import (
    TestDefinitionCreate as DefinitionCreate,
)
from atep.test_catalog.schemas import (
    TestSuiteCreate as SuiteCreate,
)
from atep.test_catalog.service import create_definition, create_suite, update_status


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


class ScalarResult:
    def __init__(self, values: list[Any]) -> None:
        self.values = values

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.values)


class FakeSession:
    def __init__(
        self, *, scalar_values: list[Any] | None = None, rows: list[Any] | None = None
    ) -> None:
        self.scalar_values = list(scalar_values or [])
        self.rows = list(rows or [])
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, _: Any) -> ScalarResult:
        return ScalarResult(self.rows)

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    async def refresh(self, _: object, *, attribute_names: list[str]) -> None:
        assert attribute_names == ["updated_at"]


def definition_command(*, name: str = "AEB lead vehicle") -> DefinitionCreate:
    return DefinitionCreate(
        definition_id="adas-aeb-lead-vehicle",
        name=name,
        description="Reusable AEB verification",
        domain="adas",
        level="system",
        automation_mode="automated",
        timeout_seconds=120,
        tags=["Safety", "Regression"],
        preconditions=["ADAS scene is active"],
        steps=[
            {
                "step_id": "approach",
                "action": "Advance the ego vehicle",
                "target": "adas-scene",
                "inputs": {"duration_ms": 1000},
                "expected": "Emergency braking is selected",
            }
        ],
    )


def definition_record(*, status: str = "active", version: int = 2) -> DefinitionRecord:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    command = definition_command()
    return DefinitionRecord(
        id=uuid4(),
        definition_id=command.definition_id,
        created_by_user_id=uuid4(),
        name=command.name,
        description=command.description,
        domain=command.domain.value,
        level=command.level.value,
        automation_mode=command.automation_mode.value,
        timeout_seconds=command.timeout_seconds,
        tags=command.tags,
        preconditions=command.preconditions,
        steps=[item.model_dump(mode="json") for item in command.steps],
        status=status,
        version=version,
        created_at=now,
        updated_at=now,
    )


def suite_command() -> SuiteCreate:
    return SuiteCreate(
        suite_id="adas-smoke-suite",
        name="ADAS smoke suite",
        suite_type="smoke",
        tags=["adas"],
        cases=[
            {
                "definition_id": "adas-aeb-lead-vehicle",
                "order": 1,
                "required": True,
                "parameter_overrides": {"speed_kph": 50},
            }
        ],
    )


def test_catalog_contracts_are_bounded_and_unambiguous() -> None:
    assert definition_command().tags == ["safety", "regression"]
    duplicate_steps = definition_command().model_dump(mode="json")
    duplicate_steps["steps"].append(duplicate_steps["steps"][0])
    with pytest.raises(ValidationError, match="step identifiers"):
        DefinitionCreate.model_validate(duplicate_steps)
    duplicate_cases = suite_command().model_dump(mode="json")
    duplicate_cases["cases"].append({**duplicate_cases["cases"][0], "order": 2})
    with pytest.raises(ValidationError, match="appear only once"):
        SuiteCreate.model_validate(duplicate_cases)


@pytest.mark.asyncio
async def test_definition_creation_is_idempotent_audited_and_evented() -> None:
    actor = uuid4()
    session = FakeSession()
    created, duplicate = await create_definition(
        cast(AsyncSession, session),
        command=definition_command(),
        actor_user_id=actor,
        correlation_id=uuid4(),
    )
    assert duplicate is False and created.status == "draft"
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.test_definition.created.v1"
    ]
    payload = next(item.payload for item in session.added if isinstance(item, OutboxEvent))
    json.dumps(payload)
    assert payload["step_count"] == 1 and "steps" not in payload
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "test_definition.created"
    ]
    created.status = "active"
    created.version = 2
    replay = FakeSession(scalar_values=[created])
    returned, duplicate = await create_definition(
        cast(AsyncSession, replay),
        command=definition_command(),
        actor_user_id=actor,
        correlation_id=None,
    )
    assert returned is created and duplicate is True and replay.added == []
    with pytest.raises(DefinitionConflictError):
        await create_definition(
            cast(AsyncSession, FakeSession(scalar_values=[created])),
            command=definition_command(name="Changed"),
            actor_user_id=actor,
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_suite_snapshots_active_definition_versions() -> None:
    definition = definition_record()
    session = FakeSession(rows=[definition])
    suite, duplicate = await create_suite(
        cast(AsyncSession, session),
        command=suite_command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert suite.composition[0]["definition_version"] == 2
    assert suite.composition[0]["name"] == "AEB lead vehicle"
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.test_suite.created.v1"
    ]
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "test_suite.created"
    ]
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.payload["case_count"] == 1 and "composition" not in event.payload

    with pytest.raises(ResourceNotFoundError):
        await create_suite(
            cast(AsyncSession, FakeSession()),
            command=suite_command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    with pytest.raises(CatalogStateError):
        await create_suite(
            cast(AsyncSession, FakeSession(rows=[definition_record(status="draft", version=1)])),
            command=suite_command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_catalog_lifecycle_is_versioned_and_forward_only() -> None:
    definition = definition_record(status="draft", version=1)
    updated, duplicate = await update_status(
        cast(AsyncSession, FakeSession()),
        resource=definition,
        command=CatalogStatusUpdate(expected_version=1, status="active"),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False and updated.status == "active" and updated.version == 2
    with pytest.raises(CatalogVersionConflictError):
        await update_status(
            cast(AsyncSession, FakeSession()),
            resource=updated,
            command=CatalogStatusUpdate(expected_version=1, status="archived"),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    suite = SuiteRecord(status="draft", version=1)
    with pytest.raises(CatalogStateError):
        await update_status(
            cast(AsyncSession, FakeSession()),
            resource=suite,
            command=CatalogStatusUpdate(expected_version=1, status="archived"),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
