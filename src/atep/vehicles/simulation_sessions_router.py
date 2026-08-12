from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.vehicles.models import Vehicle, VehicleSimulationSessionMember
from atep.vehicles.schemas import (
    SimulationSessionCreate,
    SimulationSessionResponse,
    SimulationSnapshotCreate,
    SimulationSnapshotResponse,
    SimulationSnapshotRestoreResponse,
)
from atep.vehicles.simulation_sessions import (
    capture_simulation_snapshot,
    create_simulation_session,
    require_simulation_session,
    restore_simulation_snapshot,
)

router = APIRouter(prefix="/simulation-sessions", tags=["simulation-sessions"])
digital_vehicle_read = require_permissions(PermissionName.DIGITAL_VEHICLE_READ.value)
digital_vehicle_write = require_permissions(PermissionName.DIGITAL_VEHICLE_WRITE.value)


@router.post("", response_model=SimulationSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session_endpoint(
    command: SimulationSessionCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(digital_vehicle_write)],
) -> SimulationSessionResponse:
    created, identifiers = await create_simulation_session(
        session,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(created, attribute_names=["created_at"])
    return SimulationSessionResponse(
        id=created.id,
        name=created.name,
        vehicle_ids=sorted(identifiers[member.vehicle_id] for member in created.members),
        created_at=created.created_at,
    )


@router.get("/{session_id}", response_model=SimulationSessionResponse)
async def get_session_endpoint(
    session_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(digital_vehicle_read)],
) -> SimulationSessionResponse:
    simulation_session = await require_simulation_session(session, session_id)
    identifiers = await session.execute(
        select(Vehicle)
        .join(
            VehicleSimulationSessionMember, VehicleSimulationSessionMember.vehicle_id == Vehicle.id
        )
        .where(VehicleSimulationSessionMember.session_id == session_id)
    )
    return SimulationSessionResponse(
        id=simulation_session.id,
        name=simulation_session.name,
        vehicle_ids=sorted(vehicle.identifier for vehicle in identifiers.scalars().all()),
        created_at=simulation_session.created_at,
    )


@router.post(
    "/{session_id}/snapshots",
    response_model=SimulationSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_snapshot_endpoint(
    session_id: UUID,
    command: SimulationSnapshotCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(digital_vehicle_write)],
) -> SimulationSnapshotResponse:
    simulation_session = await require_simulation_session(session, session_id)
    snapshot = await capture_simulation_snapshot(
        session,
        simulation_session=simulation_session,
        snapshot_id=command.snapshot_id,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(snapshot, attribute_names=["created_at"])
    return SimulationSnapshotResponse(
        id=snapshot.id,
        session_id=snapshot.session_id,
        snapshot_id=snapshot.snapshot_id,
        vehicle_count=len(snapshot.states),
        content_sha256=snapshot.content_sha256,
        created_at=snapshot.created_at,
    )


@router.post(
    "/{session_id}/snapshots/{snapshot_id}/restore",
    response_model=SimulationSnapshotRestoreResponse,
)
async def restore_snapshot_endpoint(
    session_id: UUID,
    snapshot_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(digital_vehicle_write)],
) -> SimulationSnapshotRestoreResponse:
    simulation_session = await require_simulation_session(session, session_id)
    restored = await restore_simulation_snapshot(
        session,
        simulation_session=simulation_session,
        snapshot_id=snapshot_id,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return SimulationSnapshotRestoreResponse(
        session_id=session_id, snapshot_id=snapshot_id, restored_vehicle_ids=restored
    )
