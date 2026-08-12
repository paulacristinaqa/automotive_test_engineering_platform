import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import ResourceNotFoundError
from atep.events.outbox import enqueue_event
from atep.vehicles.models import (
    Vehicle,
    VehicleDigitalState,
    VehicleSimulationSession,
    VehicleSimulationSessionMember,
    VehicleSimulationSnapshot,
)
from atep.vehicles.schemas import DigitalVehicleStatePayload, SimulationSessionCreate
from atep.vehicles.service import digital_state_payload


async def create_simulation_session(
    session: AsyncSession,
    *,
    command: SimulationSessionCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[VehicleSimulationSession, dict[UUID, str]]:
    rows = await session.execute(select(Vehicle).where(Vehicle.identifier.in_(command.vehicle_ids)))
    vehicles = list(rows.scalars().all())
    by_identifier = {vehicle.identifier: vehicle for vehicle in vehicles}
    if set(by_identifier) != set(command.vehicle_ids):
        raise ResourceNotFoundError("vehicle")
    simulation_session = VehicleSimulationSession(
        name=command.name, created_by_user_id=actor_user_id
    )
    simulation_session.members = [
        VehicleSimulationSessionMember(vehicle_id=by_identifier[identifier].id)
        for identifier in sorted(command.vehicle_ids)
    ]
    session.add(simulation_session)
    await session.flush()
    evidence = {
        "session_id": str(simulation_session.id),
        "name": simulation_session.name,
        "vehicle_ids": sorted(command.vehicle_ids),
    }
    enqueue_event(
        session,
        event_type="atep.digital_vehicle.session.created.v1",
        aggregate_type="simulation_session",
        aggregate_id=simulation_session.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="digital_vehicle.session_created",
        resource_type="simulation_session",
        resource_id=simulation_session.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return simulation_session, {vehicle.id: vehicle.identifier for vehicle in vehicles}


async def require_simulation_session(
    session: AsyncSession, session_id: UUID
) -> VehicleSimulationSession:
    result = await session.scalar(
        select(VehicleSimulationSession).where(VehicleSimulationSession.id == session_id)
    )
    if result is None:
        raise ResourceNotFoundError("simulation_session")
    return result


async def capture_simulation_snapshot(
    session: AsyncSession,
    *,
    simulation_session: VehicleSimulationSession,
    snapshot_id: str,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> VehicleSimulationSnapshot:
    vehicle_ids = sorted(member.vehicle_id for member in simulation_session.members)
    rows = await session.execute(
        select(Vehicle, VehicleDigitalState)
        .join(VehicleDigitalState, VehicleDigitalState.vehicle_id == Vehicle.id)
        .where(Vehicle.id.in_(vehicle_ids))
        .order_by(Vehicle.identifier)
    )
    states = sorted(
        [
            {
                "vehicle_id": vehicle.identifier,
                "version": state.version,
                "simulation_time_ms": state.simulation_time_ms,
                "state": digital_state_payload(state).model_dump(mode="json"),
            }
            for vehicle, state in rows.all()
        ],
        key=lambda item: item["vehicle_id"],
    )
    canonical = json.dumps(states, sort_keys=True, separators=(",", ":")).encode()
    snapshot = VehicleSimulationSnapshot(
        session_id=simulation_session.id,
        snapshot_id=snapshot_id,
        states=states,
        content_sha256=hashlib.sha256(canonical).hexdigest(),
        created_by_user_id=actor_user_id,
    )
    session.add(snapshot)
    await session.flush()
    evidence = {
        "session_id": str(simulation_session.id),
        "snapshot_id": snapshot_id,
        "vehicle_count": len(states),
        "content_sha256": snapshot.content_sha256,
    }
    enqueue_event(
        session,
        event_type="atep.digital_vehicle.session.snapshot-created.v1",
        aggregate_type="simulation_session",
        aggregate_id=simulation_session.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="digital_vehicle.session_snapshot_created",
        resource_type="simulation_session",
        resource_id=simulation_session.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return snapshot


async def restore_simulation_snapshot(
    session: AsyncSession,
    *,
    simulation_session: VehicleSimulationSession,
    snapshot_id: str,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> list[str]:
    snapshot = await session.scalar(
        select(VehicleSimulationSnapshot).where(
            VehicleSimulationSnapshot.session_id == simulation_session.id,
            VehicleSimulationSnapshot.snapshot_id == snapshot_id,
        )
    )
    if snapshot is None:
        raise ResourceNotFoundError("simulation_snapshot")
    identifiers = [item["vehicle_id"] for item in snapshot.states]
    rows = await session.execute(
        select(Vehicle, VehicleDigitalState)
        .join(VehicleDigitalState, VehicleDigitalState.vehicle_id == Vehicle.id)
        .where(Vehicle.identifier.in_(identifiers))
        .order_by(Vehicle.identifier)
        .with_for_update()
    )
    current = {vehicle.identifier: state for vehicle, state in rows.all()}
    if set(current) != set(identifiers):
        raise ResourceNotFoundError("simulation_session_vehicle")
    for item in snapshot.states:
        state = current[item["vehicle_id"]]
        payload = DigitalVehicleStatePayload.model_validate(item["state"])
        state.operational_mode = payload.operational_mode.value
        state.battery_state = payload.battery.model_dump(mode="json")
        state.powertrain_state = payload.powertrain.model_dump(mode="json")
        state.brake_state = payload.brakes.model_dump(mode="json")
        state.steering_state = payload.steering.model_dump(mode="json")
        state.lighting_state = payload.lighting.model_dump(mode="json")
        state.suspension_state = payload.suspension.model_dump(mode="json")
        state.simulation_time_ms = item["simulation_time_ms"]
        state.version += 1
    evidence = {
        "session_id": str(simulation_session.id),
        "snapshot_id": snapshot_id,
        "restored_vehicle_ids": identifiers,
    }
    enqueue_event(
        session,
        event_type="atep.digital_vehicle.session.snapshot-restored.v1",
        aggregate_type="simulation_session",
        aggregate_id=simulation_session.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="digital_vehicle.session_snapshot_restored",
        resource_type="simulation_session",
        resource_id=simulation_session.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return identifiers
