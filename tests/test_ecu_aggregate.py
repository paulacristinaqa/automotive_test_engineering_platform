from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import (
    EcuExecutionStateError,
    EcuProfileContractError,
    EcuSimulationCommandConflictError,
    EcuStateVersionConflictError,
)
from atep.ecus.models import EcuSimulationCommand, ElectronicControlUnit
from atep.ecus.profiles import behavior_profile, behavior_profiles
from atep.ecus.schemas import (
    EcuAdvanceCommand,
    EcuCreate,
    EcuResetCommand,
    EcuStatePayload,
    EcuStateReplace,
)
from atep.ecus.service import (
    create_ecu,
    execute_ecu_advance,
    execute_ecu_reset,
    replace_ecu_state,
)
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
        cyclic_tasks=[],
        version=version,
        simulation_time_ms=0,
        boot_count=0,
        profile_version="1.0.0",
        behavior_state={
            "cell_samples": 0,
            "soc_estimation_cycles": 0,
            "contactors_closed": False,
        },
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
    assert [task["task_id"] for task in created.cyclic_tasks] == [
        "cell_monitor",
        "soc_estimation",
    ]
    assert created.behavior_state["contactors_closed"] is False
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


def test_cyclic_task_contract_rejects_duplicate_ids_and_invalid_offsets() -> None:
    with pytest.raises(ValidationError, match="cyclic task IDs must be unique"):
        EcuStatePayload(
            cyclic_tasks=[
                {"task_id": "control_loop", "period_ms": 10},
                {"task_id": "control_loop", "period_ms": 20},
            ]
        )
    with pytest.raises(ValidationError, match="offset must be smaller"):
        EcuStatePayload(
            cyclic_tasks=[{"task_id": "control_loop", "period_ms": 10, "offset_ms": 10}]
        )
    with pytest.raises(ValidationError, match="JSON-safe"):
        EcuStatePayload(behavior_state={"unsafe_counter": 9_007_199_254_740_992})


@pytest.mark.asyncio
async def test_logical_clock_executes_cyclic_tasks_deterministically_without_sleep() -> None:
    target = vehicle()
    current = ecu()
    current.vehicle_id = target.id
    current.operational_state = "running"
    current.cyclic_tasks = [
        {"task_id": "cell_monitor", "period_ms": 100, "offset_ms": 0},
        {"task_id": "soc_estimation", "period_ms": 1000, "offset_ms": 100},
    ]
    command = EcuAdvanceCommand(
        command_id="advance-command-001", expected_version=1, duration_ms=1000
    )
    session = FakeSession(current, None)
    execution, duplicate = await execute_ecu_advance(
        cast(AsyncSession, session),
        vehicle=target,
        ecu=current,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert current.simulation_time_ms == 1000
    assert current.version == 2
    assert execution.result["task_runs"] == [
        {
            "task_id": "cell_monitor",
            "execution_count": 10,
            "first_due_ms": 100,
            "last_due_ms": 1000,
        },
        {
            "task_id": "soc_estimation",
            "execution_count": 1,
            "first_due_ms": 100,
            "last_due_ms": 100,
        },
    ]
    assert execution.result["behavior_state"]["cell_samples"] == 10
    assert execution.result["behavior_state"]["soc_estimation_cycles"] == 1
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert [item.event_type for item in events] == ["atep.ecu.simulation.advanced.v1"]
    assert audits[0].action == "ecu.simulation_advanced"
    assert audits[0].details["execution_count"] == 11

    returned, duplicate = await execute_ecu_advance(
        cast(AsyncSession, FakeSession(current, execution)),
        vehicle=target,
        ecu=current,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is execution
    assert duplicate is True


@pytest.mark.asyncio
async def test_logical_clock_rejects_offline_execution_and_stale_version() -> None:
    target = vehicle()
    current = ecu()
    current.vehicle_id = target.id
    command = EcuAdvanceCommand(
        command_id="advance-command-002", expected_version=1, duration_ms=100
    )
    with pytest.raises(EcuExecutionStateError):
        await execute_ecu_advance(
            cast(AsyncSession, FakeSession(current, None)),
            vehicle=target,
            ecu=current,
            command=command,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    current.operational_state = "running"
    current.version = 2
    with pytest.raises(EcuStateVersionConflictError):
        await execute_ecu_advance(
            cast(AsyncSession, FakeSession(current, None)),
            vehicle=target,
            ecu=current,
            command=command,
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_hard_reset_is_deterministic_and_preserves_undefined_memory_regions() -> None:
    target = vehicle()
    current = ecu()
    current.vehicle_id = target.id
    current.operational_state = "running"
    current.simulation_time_ms = 1000
    current.memory = [{"address": 1, "value": 7}]
    current.faults = [
        {
            "code": "BMS_WARN",
            "severity": "warning",
            "status": "confirmed",
            "description": "",
        }
    ]
    command = EcuResetCommand(command_id="reset-command-001", expected_version=1, mode="hard")
    session = FakeSession(current, None)
    execution, duplicate = await execute_ecu_reset(
        cast(AsyncSession, session),
        vehicle=target,
        ecu=current,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert current.operational_state == "offline"
    assert current.simulation_time_ms == 1100
    assert current.boot_count == 1
    assert current.memory == [{"address": 1, "value": 7}]
    assert execution.result == {
        "mode": "hard",
        "reset_duration_ms": 100,
        "boot_count": 1,
        "memory_preserved": True,
        "faults_preserved": True,
    }
    assert [
        item.event_type for item in session.added if isinstance(item, OutboxEvent)
    ] == ["atep.ecu.reset.completed.v1"]

    returned, duplicate = await execute_ecu_reset(
        cast(AsyncSession, FakeSession(current, execution)),
        vehicle=target,
        ecu=current,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is execution
    assert duplicate is True
    assert current.boot_count == 1


@pytest.mark.parametrize(
    ("mode", "duration_ms"), [("soft", 10), ("hard", 100), ("power_cycle", 500)]
)
@pytest.mark.asyncio
async def test_reset_modes_have_fixed_logical_durations(mode: str, duration_ms: int) -> None:
    target = vehicle()
    current = ecu()
    current.vehicle_id = target.id
    execution, _ = await execute_ecu_reset(
        cast(AsyncSession, FakeSession(current, None)),
        vehicle=target,
        ecu=current,
        command=EcuResetCommand(
            command_id=f"reset-{mode}-command", expected_version=1, mode=mode
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert execution.simulation_time_ms == duration_ms
    assert execution.result["reset_duration_ms"] == duration_ms


@pytest.mark.asyncio
async def test_simulation_command_id_cannot_be_reused_for_different_input() -> None:
    target = vehicle()
    current = ecu()
    current.vehicle_id = target.id
    current.operational_state = "running"
    existing = EcuSimulationCommand(
        id=uuid4(),
        ecu_id=current.id,
        command_id="shared-command-001",
        kind="advance",
        request={"command_id": "shared-command-001", "expected_version": 1, "duration_ms": 100},
        result={"duration_ms": 100, "task_runs": []},
        previous_version=1,
        state_version=2,
        previous_time_ms=0,
        simulation_time_ms=100,
        requested_by_user_id=uuid4(),
    )
    with pytest.raises(EcuSimulationCommandConflictError):
        await execute_ecu_advance(
            cast(AsyncSession, FakeSession(current, existing)),
            vehicle=target,
            ecu=current,
            command=EcuAdvanceCommand(
                command_id="shared-command-001", expected_version=1, duration_ms=200
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


def test_profile_registry_covers_every_supported_ecu_type_with_versioned_tasks() -> None:
    profiles = behavior_profiles()
    assert len(profiles) == 9
    assert {profile.ecu_type.value for profile in profiles} == {
        "motor",
        "battery",
        "door",
        "abs",
        "adas",
        "climate",
        "gateway",
        "lighting",
        "body",
    }
    assert all(profile.profile_version == "1.0.0" for profile in profiles)
    assert [task.task_id for task in behavior_profile("motor").tasks] == [
        "torque_control",
        "motor_thermal",
    ]


@pytest.mark.asyncio
async def test_profile_rejects_unknown_tasks_before_state_is_persisted() -> None:
    target = vehicle()
    current = ecu()
    current.vehicle_id = target.id
    with pytest.raises(EcuProfileContractError) as error:
        await replace_ecu_state(
            cast(AsyncSession, FakeSession(current)),
            vehicle=target,
            ecu=current,
            command=EcuStateReplace(
                expected_version=1,
                cyclic_tasks=[{"task_id": "untrusted_loop", "period_ms": 10}],
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.code == "ecu_profile_contract_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        EcuStateReplace(
            expected_version=1,
            cyclic_tasks=[{"task_id": "cell_monitor", "period_ms": 101}],
        ),
        EcuStateReplace(expected_version=1, behavior_state={"unknown_counter": 1}),
    ],
)
async def test_profile_rejects_schedule_drift_and_unknown_state_keys(
    state: EcuStateReplace,
) -> None:
    target = vehicle()
    current = ecu()
    current.vehicle_id = target.id
    with pytest.raises(EcuProfileContractError):
        await replace_ecu_state(
            cast(AsyncSession, FakeSession(current)),
            vehicle=target,
            ecu=current,
            command=state,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
