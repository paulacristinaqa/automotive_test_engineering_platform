from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import EcuStateVersionConflictError
from atep.ecus.models import ElectronicControlUnit
from atep.ecus.schemas import EcuCreate, EcuStatePayload, EcuStateReplace
from atep.ecus.service import create_ecu, replace_ecu_state
from atep.events.models import OutboxEvent
from atep.identity.dependencies import require_permissions
from atep.identity.permissions import PermissionName
from atep.vehicles.models import Vehicle


class FakeSession:
    def __init__(self, *scalar_values: Any) -> None:
        self.scalar_values = list(scalar_values)
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    async def refresh(self, _: object, *, attribute_names: list[str]) -> None:
        assert attribute_names == ["updated_at"]

    def begin_nested(self) -> Any:
        class Transaction:
            async def __aenter__(self) -> None:
                return None

            async def __aexit__(self, *_: object) -> None:
                return None

        return Transaction()


def vehicle() -> Vehicle:
    now = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP Reference Vehicle",
        model="EV",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def ecu(*, version: int = 1) -> ElectronicControlUnit:
    now = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
    return ElectronicControlUnit(
        id=uuid4(),
        vehicle_id=uuid4(),
        identifier="bms-ecu",
        display_name="Battery Management ECU",
        ecu_type="battery",
        operational_state="offline",
        memory=[],
        faults=[],
        version=version,
        created_at=now,
        updated_at=now,
    )


def running_state(*, expected_version: int = 1) -> EcuStateReplace:
    return EcuStateReplace(
        expected_version=expected_version,
        operational_state="running",
        memory=[{"address": 16, "value": 127}],
        faults=[
            {
                "code": "BATT_TEMP_WARN",
                "severity": "warning",
                "status": "confirmed",
                "description": "Battery temperature above nominal range",
            }
        ],
    )


def test_ecu_state_contract_enforces_bounded_unique_memory_and_faults() -> None:
    with pytest.raises(ValidationError, match="memory addresses must be unique"):
        EcuStatePayload(memory=[{"address": 1, "value": 2}, {"address": 1, "value": 3}])
    with pytest.raises(ValidationError, match="fault codes must be unique"):
        EcuStatePayload(
            faults=[
                {"code": "P0A80", "severity": "warning"},
                {"code": "P0A80", "severity": "warning"},
            ]
        )
    with pytest.raises(ValidationError, match="critical fault requires"):
        EcuStatePayload(
            operational_state="degraded",
            faults=[{"code": "BMS_FATAL", "severity": "critical", "status": "confirmed"}],
        )
    with pytest.raises(ValidationError, match="less than or equal to 255"):
        EcuStatePayload(memory=[{"address": 1, "value": 256}])


@pytest.mark.asyncio
async def test_ecu_creation_is_audited_and_evented_atomically() -> None:
    target = vehicle()
    session = FakeSession(None)
    created = await create_ecu(
        cast(AsyncSession, session),
        vehicle=target,
        command=EcuCreate(
            identifier="bms-ecu",
            display_name="Battery Management ECU",
            ecu_type="battery",
        ),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert created.version == 1
    assert created.operational_state == "offline"
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert [item.event_type for item in events] == ["atep.ecu.created.v1"]
    assert events[0].payload["vehicle_id"] == target.identifier
    assert [item.action for item in audits] == ["ecu.created"]
    assert "state" not in audits[0].details


@pytest.mark.asyncio
async def test_ecu_state_replace_is_versioned_idempotent_and_evidence_safe() -> None:
    target = vehicle()
    current = ecu()
    current.vehicle_id = target.id
    session = FakeSession(current)
    updated, duplicate = await replace_ecu_state(
        cast(AsyncSession, session),
        vehicle=target,
        ecu=current,
        command=running_state(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert updated.version == 2
    assert updated.memory == [{"address": 16, "value": 127}]
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert [item.event_type for item in events] == ["atep.ecu.state.updated.v1"]
    assert audits[0].details["memory_cell_count"] == 1
    assert "state" not in audits[0].details

    retry, duplicate = await replace_ecu_state(
        cast(AsyncSession, FakeSession(current)),
        vehicle=target,
        ecu=current,
        command=running_state(expected_version=1),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert retry is current
    assert duplicate is True

    with pytest.raises(EcuStateVersionConflictError) as error:
        await replace_ecu_state(
            cast(AsyncSession, FakeSession(current)),
            vehicle=target,
            ecu=current,
            command=EcuStateReplace(expected_version=1),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details == {"current_version": 2}


def test_ecu_permissions_are_independent() -> None:
    assert PermissionName.ECUS_READ.value == "ecus:read"
    assert PermissionName.ECUS_MANAGE.value == "ecus:manage"
    assert require_permissions(PermissionName.ECUS_READ.value) is not None
