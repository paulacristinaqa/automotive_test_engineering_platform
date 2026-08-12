from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import VehicleStateVersionConflictError
from atep.events.models import OutboxEvent
from atep.identity.dependencies import require_permissions
from atep.identity.permissions import PermissionName
from atep.vehicles.models import Vehicle, VehicleDigitalState
from atep.vehicles.schemas import (
    DigitalVehicleStatePayload,
    DigitalVehicleStateReplace,
    VehicleCreate,
)
from atep.vehicles.service import create_vehicle, replace_vehicle_digital_state


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
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP Digital Vehicle",
        model="EV Reference Platform",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def state() -> VehicleDigitalState:
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    baseline = DigitalVehicleStatePayload()
    return VehicleDigitalState(
        id=uuid4(),
        vehicle_id=uuid4(),
        operational_mode=baseline.operational_mode.value,
        battery_state=baseline.battery.model_dump(mode="json"),
        powertrain_state=baseline.powertrain.model_dump(mode="json"),
        brake_state=baseline.brakes.model_dump(mode="json"),
        steering_state=baseline.steering.model_dump(mode="json"),
        lighting_state=baseline.lighting.model_dump(mode="json"),
        version=1,
        created_at=now,
        updated_at=now,
    )


def driving_command(*, expected_version: int = 1) -> DigitalVehicleStateReplace:
    return DigitalVehicleStateReplace(
        expected_version=expected_version,
        operational_mode="driving",
        battery={
            "state_of_charge_pct": 79.5,
            "state_of_health_pct": 99.8,
            "pack_voltage_v": 398.0,
            "pack_current_a": 120.0,
            "temperature_c": 31.0,
            "contactors_closed": True,
            "charging_status": "disconnected",
        },
        powertrain={
            "motor_enabled": True,
            "gear": "drive",
            "speed_kph": 45.0,
            "requested_torque_nm": 180.0,
            "delivered_torque_nm": 176.0,
        },
        brakes={
            "pedal_pct": 0.0,
            "hydraulic_pressure_bar": 0.0,
            "parking_brake_applied": False,
            "abs_active": False,
        },
        steering={"wheel_angle_deg": 3.5, "assist_active": True},
        lighting={"exterior_mode": "auto", "brake_lights": False, "indicator": "off"},
    )


def test_digital_vehicle_defaults_are_safe_and_bounded() -> None:
    baseline = DigitalVehicleStatePayload()
    assert baseline.operational_mode == "parked"
    assert baseline.powertrain.gear == "park"
    assert baseline.brakes.parking_brake_applied is True
    assert baseline.battery.contactors_closed is False

    with pytest.raises(ValidationError, match="less than or equal to 100"):
        DigitalVehicleStatePayload(battery={"state_of_charge_pct": 101})


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "operational_mode": "parked",
                "powertrain": {"motor_enabled": True, "gear": "drive", "speed_kph": 10},
                "brakes": {"parking_brake_applied": False},
                "battery": {"contactors_closed": True},
            },
            "moving vehicle must be in driving mode",
        ),
        (
            {
                "operational_mode": "charging",
                "battery": {"charging_status": "charging", "contactors_closed": False},
            },
            "charging requires",
        ),
        (
            {"powertrain": {"motor_enabled": False, "requested_torque_nm": 10}},
            "disabled motor",
        ),
    ],
)
def test_cross_component_invariants_reject_impossible_states(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        DigitalVehicleStatePayload.model_validate(payload)


@pytest.mark.asyncio
async def test_vehicle_registration_creates_safe_digital_state() -> None:
    session = FakeSession()
    registered = await create_vehicle(
        cast(AsyncSession, session),
        command=VehicleCreate(identifier="vehicle-001", display_name="Digital Vehicle"),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert registered.digital_state.operational_mode == "parked"
    assert registered.digital_state.version == 1
    assert registered.digital_state.brake_state["parking_brake_applied"] is True


@pytest.mark.asyncio
async def test_state_replace_is_versioned_audited_and_evented_atomically() -> None:
    target = vehicle()
    current = state()
    current.vehicle_id = target.id
    session = FakeSession(current)
    updated, duplicate = await replace_vehicle_digital_state(
        cast(AsyncSession, session),
        vehicle=target,
        command=driving_command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert updated.version == 2
    assert updated.operational_mode == "driving"
    assert updated.powertrain_state["speed_kph"] == 45.0
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert [item.event_type for item in events] == ["atep.digital_vehicle.state.updated.v1"]
    assert events[0].payload["previous_version"] == 1
    assert [item.action for item in audits] == ["digital_vehicle.state_updated"]
    assert "state" not in audits[0].details


@pytest.mark.asyncio
async def test_exact_retry_is_idempotent_but_stale_different_state_conflicts() -> None:
    target = vehicle()
    current = state()
    current.vehicle_id = target.id
    await replace_vehicle_digital_state(
        cast(AsyncSession, FakeSession(current)),
        vehicle=target,
        command=driving_command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    retry_session = FakeSession(current)
    returned, duplicate = await replace_vehicle_digital_state(
        cast(AsyncSession, retry_session),
        vehicle=target,
        command=driving_command(expected_version=1),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is current
    assert duplicate is True
    assert retry_session.added == []

    with pytest.raises(VehicleStateVersionConflictError) as error:
        await replace_vehicle_digital_state(
            cast(AsyncSession, FakeSession(current)),
            vehicle=target,
            command=DigitalVehicleStateReplace(expected_version=1),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details == {"current_version": 2}


def test_digital_vehicle_permissions_are_independent() -> None:
    assert PermissionName.DIGITAL_VEHICLE_READ.value == "digital_vehicle:read"
    assert PermissionName.DIGITAL_VEHICLE_WRITE.value == "digital_vehicle:write"
    assert require_permissions(PermissionName.DIGITAL_VEHICLE_READ.value) is not None
