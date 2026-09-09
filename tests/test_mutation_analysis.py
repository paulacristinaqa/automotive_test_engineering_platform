from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import MutantResultStateError, MutationCampaignStateError
from atep.events.models import OutboxEvent
from atep.mutation_analysis.models import MutantResult, MutationCampaign, MutationExecution
from atep.mutation_analysis.schemas import (
    CampaignStatusUpdate,
    MutantResultUpdate,
    MutationCampaignCreate,
    MutationExecutionCreate,
    RequirementCoverageUpsert,
    coverage_status,
)
from atep.mutation_analysis.service import (
    create_campaign,
    create_execution,
    update_campaign_status,
    update_result,
    upsert_requirement_coverage,
)
from atep.test_catalog.models import TestDefinition as CatalogDefinition
from atep.test_catalog.models import TestSuite as CatalogSuite
from atep.vehicles.models import Vehicle


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


class ScalarRows:
    def __init__(self, values: list[Any]) -> None:
        self.values = values

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.values)


class FakeSession:
    def __init__(self, *scalar_values: Any, scalar_rows: list[list[Any]] | None = None) -> None:
        self.scalar_values = list(scalar_values)
        self.scalar_rows = list(scalar_rows or [])
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, _: Any) -> ScalarRows:
        return ScalarRows(self.scalar_rows.pop(0) if self.scalar_rows else [])

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    async def refresh(self, _: Any, *, attribute_names: list[str]) -> None:
        assert attribute_names == ["updated_at"]


NOW = datetime(2026, 9, 9, 10, 0, tzinfo=UTC)


def suite() -> CatalogSuite:
    return CatalogSuite(
        id=uuid4(),
        suite_id="safety-suite-001",
        created_by_user_id=uuid4(),
        name="Safety regression",
        description="",
        suite_type="regression",
        composition=[
            {
                "definition_id": "battery-test-001",
                "order": 1,
                "required": True,
                "parameter_overrides": {},
                "definition_version": 1,
                "name": "Battery",
            }
        ],
        tags=["safety"],
        status="active",
        version=2,
        created_at=NOW,
        updated_at=NOW,
    )


def command() -> MutationCampaignCreate:
    return MutationCampaignCreate(
        campaign_id="mutation-campaign-001",
        catalog_suite_id="safety-suite-001",
        name="Safety mutation baseline",
        tags=["Safety"],
        mutants=[
            {
                "mutant_id": "boundary-soc",
                "order": 1,
                "operator": "boundary_shift",
                "target": "battery.soc_limit",
                "parameters": {"delta": 1},
                "expected_detection": "Battery boundary test fails",
            },
            {
                "mutant_id": "invert-brake",
                "order": 2,
                "operator": "conditional_negation",
                "target": "braking.regen_guard",
                "expected_detection": "Brake invariant fails",
                "required": False,
            },
        ],
    )


def vehicle() -> Vehicle:
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP EV",
        model="EV Reference",
        description="",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )


def campaign(source: CatalogSuite, *, status: str = "active") -> MutationCampaign:
    request = command()
    return MutationCampaign(
        id=uuid4(),
        campaign_id=request.campaign_id,
        created_by_user_id=uuid4(),
        catalog_suite_id=source.id,
        suite_version=source.version,
        suite_snapshot={
            "suite_id": source.suite_id,
            "name": source.name,
            "suite_type": source.suite_type,
            "version": source.version,
            "composition": source.composition,
            "tags": source.tags,
        },
        name=request.name,
        description=request.description,
        mutants=[item.model_dump(mode="json") for item in request.mutants],
        tags=request.tags,
        status=status,
        version=2 if status == "active" else 1,
        created_at=NOW,
        updated_at=NOW,
    )


def execution(source: MutationCampaign, target: Vehicle) -> MutationExecution:
    return MutationExecution(
        id=uuid4(),
        execution_id="mutation-run-0001",
        campaign_id=source.id,
        campaign_version=source.version,
        campaign_snapshot={
            "campaign_id": source.campaign_id,
            "name": source.name,
            "suite": source.suite_snapshot,
            "mutants": source.mutants,
            "tags": source.tags,
            "test_run_id": None,
        },
        vehicle_id=target.id,
        test_run_id=None,
        requested_by_user_id=uuid4(),
        status="queued",
        total_mutants=2,
        completed_mutants=0,
        killed_mutants=0,
        survived_mutants=0,
        mutation_score=None,
        version=1,
        started_at=None,
        completed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def mutant(run: MutationExecution, *, required: bool = True) -> MutantResult:
    return MutantResult(
        id=uuid4(),
        execution_id=run.id,
        mutant_id="boundary-soc",
        order=1,
        operator="boundary_shift",
        target="battery.soc_limit",
        required=required,
        status="pending",
        duration_ms=None,
        detected_by=[],
        evidence_refs=[],
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )


def test_contract_bounds_operators_and_mutants() -> None:
    assert command().mutants[0].operator.value == "boundary_shift"
    payload = command().model_dump()
    payload["mutants"][0]["operator"] = "shell_command"
    with pytest.raises(ValidationError):
        MutationCampaignCreate(**payload)
    payload = command().model_dump()
    payload["mutants"][1]["order"] = 1
    with pytest.raises(ValidationError, match="order"):
        MutationCampaignCreate(**payload)


@pytest.mark.asyncio
async def test_campaign_is_snapshot_based_idempotent_and_evented() -> None:
    source = suite()
    actor = uuid4()
    session = FakeSession(None)
    created, duplicate = await create_campaign(
        cast(AsyncSession, session),
        command=command(),
        suite=source,
        actor_user_id=actor,
        correlation_id=uuid4(),
        now=NOW,
    )
    assert duplicate is False
    assert created.status == "draft"
    assert created.suite_version == 2
    source.composition[0]["name"] = "Changed"
    assert created.suite_snapshot["composition"][0]["name"] == "Battery"
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.mutation_campaign.created.v1"
    assert event.payload["mutant_count"] == 2
    assert "mutants" not in event.payload
    assert (
        next(item for item in session.added if isinstance(item, AuditRecord)).action
        == "mutation_campaign.created"
    )

    retry = FakeSession(created)
    returned, duplicate = await create_campaign(
        cast(AsyncSession, retry),
        command=command(),
        suite=source,
        actor_user_id=actor,
        correlation_id=None,
    )
    assert returned is created
    assert duplicate is True


@pytest.mark.asyncio
async def test_campaign_lifecycle_is_forward_only() -> None:
    source = campaign(suite(), status="draft")
    updated, _ = await update_campaign_status(
        cast(AsyncSession, FakeSession()),
        campaign=source,
        command=CampaignStatusUpdate(expected_version=1, status="active"),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    with pytest.raises(MutationCampaignStateError):
        await update_campaign_status(
            cast(AsyncSession, FakeSession()),
            campaign=updated,
            command=CampaignStatusUpdate(expected_version=2, status="draft"),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_execution_materializes_mutants_and_exact_replay_survives_archive() -> None:
    source = campaign(suite())
    target = vehicle()
    actor = uuid4()
    request = MutationExecutionCreate(
        execution_id="mutation-run-0001", vehicle_id=target.identifier
    )
    session = FakeSession(None)
    created, duplicate = await create_execution(
        cast(AsyncSession, session),
        campaign=source,
        command=request,
        vehicle=target,
        test_run=None,
        actor_user_id=actor,
        correlation_id=None,
        now=NOW,
    )
    assert duplicate is False
    assert len([item for item in session.added if isinstance(item, MutantResult)]) == 2
    assert created.total_mutants == 2
    source.status = "archived"
    created.requested_by_user_id = actor
    returned, duplicate = await create_execution(
        cast(AsyncSession, FakeSession(created)),
        campaign=source,
        command=request,
        vehicle=target,
        test_run=None,
        actor_user_id=actor,
        correlation_id=None,
    )
    assert returned is created
    assert duplicate is True


@pytest.mark.asyncio
async def test_results_derive_kill_rate_and_required_survivor_failure() -> None:
    source = campaign(suite())
    target = vehicle()
    run = execution(source, target)
    killed = mutant(run)
    optional = mutant(run, required=False)
    optional.id = uuid4()
    optional.mutant_id = "invert-brake"
    optional.status = "survived"
    await update_result(
        cast(AsyncSession, FakeSession(scalar_rows=[[killed, optional]])),
        execution=run,
        campaign=source,
        vehicle=target,
        result=killed,
        command=MutantResultUpdate(expected_version=1, status="running"),
        actor_user_id=uuid4(),
        correlation_id=None,
        now=NOW,
    )
    await update_result(
        cast(AsyncSession, FakeSession(scalar_rows=[[killed, optional]])),
        execution=run,
        campaign=source,
        vehicle=target,
        result=killed,
        command=MutantResultUpdate(
            expected_version=2,
            status="killed",
            duration_ms=20,
            detected_by=["battery-test-001"],
            evidence_refs=["artifact://pytest.xml"],
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
        now=NOW,
    )
    assert run.status == "passed"
    assert run.mutation_score == 0.5
    assert run.killed_mutants == 1
    assert run.survived_mutants == 1

    invalid = mutant(execution(source, target))
    with pytest.raises(MutantResultStateError):
        await update_result(
            cast(AsyncSession, FakeSession()),
            execution=run,
            campaign=source,
            vehicle=target,
            result=invalid,
            command=MutantResultUpdate(
                expected_version=1, status="killed", duration_ms=1, detected_by=["battery-test-001"]
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


def test_coverage_classifies_covered_partial_and_gap() -> None:
    assert coverage_status([], []).value == "gap"
    assert coverage_status(["battery-test-001"], []).value == "partial"
    assert coverage_status(["battery-test-001"], ["artifact://report"]).value == "covered"


@pytest.mark.asyncio
async def test_requirement_coverage_validates_definitions_and_minimizes_evidence() -> None:
    definition = CatalogDefinition(
        id=uuid4(),
        definition_id="battery-test-001",
        created_by_user_id=uuid4(),
        name="Battery",
        description="",
        domain="electric_vehicle",
        level="system",
        automation_mode="automated",
        timeout_seconds=30,
        tags=[],
        preconditions=[],
        steps=[],
        status="active",
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    session = FakeSession(None, scalar_rows=[[definition]])
    item, duplicate = await upsert_requirement_coverage(
        cast(AsyncSession, session),
        requirement_id="EV-F-001",
        command=RequirementCoverageUpsert(
            title="Battery state remains bounded",
            criticality="asil_b",
            definition_ids=["battery-test-001"],
            evidence_refs=["artifact://report"],
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
        now=NOW,
    )
    assert duplicate is False
    assert item.status == "covered"
    event = next(value for value in session.added if isinstance(value, OutboxEvent))
    assert event.payload["definition_count"] == 1
    assert event.payload["evidence_count"] == 1
    assert "evidence_refs" not in event.payload
