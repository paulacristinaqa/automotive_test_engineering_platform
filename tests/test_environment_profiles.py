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
    EnvironmentProfileConflictError as ProfileConflictError,
)
from atep.core.errors import (
    EnvironmentProfileStateError as ProfileStateError,
)
from atep.core.errors import (
    EnvironmentProfileVersionConflictError as ProfileVersionConflictError,
)
from atep.environment_profiles.models import EnvironmentProfile as ProfileRecord
from atep.environment_profiles.schemas import (
    EnvironmentProfileCreate as ProfileCreate,
)
from atep.environment_profiles.schemas import (
    EnvironmentProfileStatusUpdate as ProfileStatusUpdate,
)
from atep.environment_profiles.service import (
    create_environment_profile,
    update_environment_profile_status,
)
from atep.events.models import OutboxEvent
from atep.test_runs.schemas import TestRunCreate as RunCreate
from atep.test_runs.service import create_test_run
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


class FakeSession:
    def __init__(self, *scalar_values: Any) -> None:
        self.scalar_values = list(scalar_values)
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

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


def profile_command(*, name: str = "EV simulator baseline") -> ProfileCreate:
    return ProfileCreate(
        profile_id="ev-simulator-baseline",
        name=name,
        description="Reproducible battery and powertrain baseline",
        vehicle_kind="electric",
        property_source="simulator",
        configuration={"battery_level": 80, "ambient_temperature_c": 22.0},
    )


def profile_record(*, status: str = "draft", version: int = 1) -> ProfileRecord:
    now = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)
    command = profile_command()
    return ProfileRecord(
        id=uuid4(),
        profile_id=command.profile_id,
        created_by_user_id=uuid4(),
        name=command.name,
        description=command.description,
        vehicle_kind=command.vehicle_kind.value,
        property_source=command.property_source.value,
        configuration=command.configuration,
        status=status,
        version=version,
        created_at=now,
        updated_at=now,
    )


def vehicle() -> Vehicle:
    now = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP Development Vehicle",
        model="EV Reference Platform",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_profile_contract_bounds_identity_and_configuration() -> None:
    with pytest.raises(ValidationError, match="lowercase URL-safe"):
        ProfileCreate(
            profile_id="unsafe profile",
            name="Unsafe",
            vehicle_kind="electric",
            property_source="simulator",
        )
    with pytest.raises(ValidationError, match="16384 bytes"):
        ProfileCreate(
            profile_id="large-profile",
            name="Large",
            vehicle_kind="electric",
            property_source="simulator",
            configuration={"payload": "x" * 17_000},
        )


@pytest.mark.asyncio
async def test_profile_creation_is_idempotent_audited_and_evented() -> None:
    actor_id = uuid4()
    session = FakeSession()
    created, duplicate = await create_environment_profile(
        cast(AsyncSession, session),
        command=profile_command(),
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert created.status == "draft"
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.environment_profile.created.v1"
    ]
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "environment_profile.created"
    ]

    retry = FakeSession(created)
    returned, duplicate = await create_environment_profile(
        cast(AsyncSession, retry),
        command=profile_command(),
        actor_user_id=actor_id,
        correlation_id=None,
    )
    assert returned is created
    assert duplicate is True
    assert retry.added == []

    with pytest.raises(ProfileConflictError):
        await create_environment_profile(
            cast(AsyncSession, FakeSession(created)),
            command=profile_command(name="Changed"),
            actor_user_id=actor_id,
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_profile_lifecycle_enforces_version_and_state() -> None:
    actor_id = uuid4()
    profile = profile_record()
    session = FakeSession()
    activated, duplicate = await update_environment_profile_status(
        cast(AsyncSession, session),
        profile=profile,
        command=ProfileStatusUpdate(expected_version=1, status="active"),
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert activated.status == "active"
    assert activated.version == 2
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.environment_profile.status_changed.v1"
    ]

    with pytest.raises(ProfileVersionConflictError):
        await update_environment_profile_status(
            cast(AsyncSession, FakeSession()),
            profile=activated,
            command=ProfileStatusUpdate(expected_version=1, status="archived"),
            actor_user_id=actor_id,
            correlation_id=None,
        )

    draft = profile_record()
    with pytest.raises(ProfileStateError):
        await update_environment_profile_status(
            cast(AsyncSession, FakeSession()),
            profile=draft,
            command=ProfileStatusUpdate(expected_version=1, status="archived"),
            actor_user_id=actor_id,
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_test_run_captures_active_profile_snapshot() -> None:
    target = vehicle()
    profile = profile_record(status="active", version=2)
    session = FakeSession()
    test_run, _ = await create_test_run(
        cast(AsyncSession, session),
        command=RunCreate(
            run_id="01JXYZPROFILETEST1",
            vehicle_id=target.identifier,
            environment_profile_id=profile.profile_id,
            name="Profile-backed smoke test",
            suite="smoke",
        ),
        vehicle=target,
        environment_profile=profile,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert test_run.environment_profile_id == profile.id
    assert test_run.environment_profile_version == 2
    assert test_run.environment_snapshot == {
        "profile_id": profile.profile_id,
        "name": profile.name,
        "vehicle_kind": "electric",
        "property_source": "simulator",
        "configuration": profile.configuration,
    }
