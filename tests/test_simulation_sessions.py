from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.events.models import OutboxEvent
from atep.vehicles.models import (
    Vehicle,
    VehicleDigitalState,
    VehicleSimulationSession,
    VehicleSimulationSessionMember,
)
from atep.vehicles.schemas import DigitalVehicleStatePayload, SimulationSessionCreate
from atep.vehicles.simulation_sessions import (
    capture_simulation_snapshot,
    create_simulation_session,
    restore_simulation_snapshot,
)


class Result:
    def __init__(self, values: list[Any]) -> None:
        self.values = values

    def scalars(self) -> "Result":
        return self

    def all(self) -> list[Any]:
        return self.values


class Session:
    def __init__(
        self, *, execute_values: list[list[Any]] | None = None, scalar: Any = None
    ) -> None:
        self.execute_values = list(execute_values or [])
        self.scalar_value = scalar
        self.added: list[Any] = []

    async def execute(self, _: Any) -> Result:
        return Result(self.execute_values.pop(0))

    async def scalar(self, _: Any) -> Any:
        return self.scalar_value

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()
        for value in self.added:
            if isinstance(value, VehicleSimulationSession):
                for member in value.members:
                    member.session_id = value.id
                    if member.id is None:
                        member.id = uuid4()


def vehicle(identifier: str) -> Vehicle:
    now = datetime(2026, 8, 12, 14, 0, tzinfo=UTC)
    return Vehicle(
        id=uuid4(),
        identifier=identifier,
        display_name=identifier,
        model="EV",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def digital_state(target: Vehicle, *, speed: float, version: int) -> VehicleDigitalState:
    now = datetime(2026, 8, 12, 14, 0, tzinfo=UTC)
    payload = DigitalVehicleStatePayload(
        operational_mode="driving",
        battery={"contactors_closed": True},
        powertrain={"motor_enabled": True, "gear": "drive", "speed_kph": speed},
        brakes={"parking_brake_applied": False},
    )
    return VehicleDigitalState(
        id=uuid4(),
        vehicle_id=target.id,
        operational_mode=payload.operational_mode.value,
        battery_state=payload.battery.model_dump(mode="json"),
        powertrain_state=payload.powertrain.model_dump(mode="json"),
        brake_state=payload.brakes.model_dump(mode="json"),
        steering_state=payload.steering.model_dump(mode="json"),
        lighting_state=payload.lighting.model_dump(mode="json"),
        suspension_state=payload.suspension.model_dump(mode="json"),
        version=version,
        simulation_time_ms=version * 1000,
        created_at=now,
        updated_at=now,
    )


def simulation_session(*vehicles: Vehicle) -> VehicleSimulationSession:
    created = VehicleSimulationSession(
        id=uuid4(), name="Fleet scenario", created_by_user_id=uuid4()
    )
    created.members = [
        VehicleSimulationSessionMember(id=uuid4(), session_id=created.id, vehicle_id=item.id)
        for item in vehicles
    ]
    return created


def test_session_contract_bounds_size_and_uniqueness() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        SimulationSessionCreate(name="Fleet", vehicle_ids=["vehicle-001", "vehicle-001"])
    with pytest.raises(ValidationError, match="at most 20"):
        SimulationSessionCreate(name="Fleet", vehicle_ids=[f"vehicle-{i:03}" for i in range(21)])


@pytest.mark.asyncio
async def test_session_creation_orders_members_and_records_atomic_evidence() -> None:
    first, second = vehicle("vehicle-001"), vehicle("vehicle-002")
    fake = Session(execute_values=[[second, first]])
    created, identifiers = await create_simulation_session(
        cast(AsyncSession, fake),
        command=SimulationSessionCreate(
            name=" Fleet scenario ", vehicle_ids=[second.identifier, first.identifier]
        ),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert created.name == "Fleet scenario"
    assert [identifiers[item.vehicle_id] for item in created.members] == [
        "vehicle-001",
        "vehicle-002",
    ]
    assert [type(item) for item in fake.added] == [
        VehicleSimulationSession,
        OutboxEvent,
        AuditRecord,
    ]


@pytest.mark.asyncio
async def test_snapshot_is_canonical_and_restore_keeps_vehicle_states_isolated() -> None:
    first, second = vehicle("vehicle-001"), vehicle("vehicle-002")
    first_state = digital_state(first, speed=20, version=2)
    second_state = digital_state(second, speed=70, version=5)
    group = simulation_session(first, second)
    capture_session = Session(execute_values=[[(second, second_state), (first, first_state)]])
    snapshot = await capture_simulation_snapshot(
        cast(AsyncSession, capture_session),
        simulation_session=group,
        snapshot_id="snapshot-fleet-001",
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert [item["vehicle_id"] for item in snapshot.states] == ["vehicle-001", "vehicle-002"]
    assert len(snapshot.content_sha256) == 64

    first_state.powertrain_state["speed_kph"] = 99
    second_state.powertrain_state["speed_kph"] = 1
    restore_session = Session(
        execute_values=[[(first, first_state), (second, second_state)]], scalar=snapshot
    )
    restored = await restore_simulation_snapshot(
        cast(AsyncSession, restore_session),
        simulation_session=group,
        snapshot_id=snapshot.snapshot_id,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert restored == ["vehicle-001", "vehicle-002"]
    assert first_state.powertrain_state["speed_kph"] == 20
    assert second_state.powertrain_state["speed_kph"] == 70
    assert first_state.version == 3
    assert second_state.version == 6
    assert [type(item) for item in restore_session.added] == [OutboxEvent, AuditRecord]
