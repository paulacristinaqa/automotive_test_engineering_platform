from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.ecus.models import EcuMemorySnapshot, EcuSimulationCommand, ElectronicControlUnit
from atep.ecus.profiles import behavior_profile, behavior_profiles
from atep.ecus.schemas import (
    EcuAdvanceCommand,
    EcuAdvanceResponse,
    EcuBehaviorProfileResponse,
    EcuCreate,
    EcuDtcCandidatePage,
    EcuFault,
    EcuFaultClearCommand,
    EcuFaultLifecycleResponse,
    EcuFaultObservationCommand,
    EcuMemoryChange,
    EcuMemoryCorruptionCommand,
    EcuMemoryCorruptionResponse,
    EcuMemorySnapshotPage,
    EcuMemorySnapshotResponse,
    EcuPage,
    EcuProfileTaskResponse,
    EcuResetCommand,
    EcuResetResponse,
    EcuResponse,
    EcuSnapshotCreate,
    EcuSnapshotRestoreCommand,
    EcuStateReplace,
    EcuTaskRunSummary,
    EcuType,
)
from atep.ecus.service import (
    clear_ecu_fault,
    corrupt_ecu_memory,
    create_ecu,
    create_memory_snapshot,
    dtc_candidates,
    ecu_state_payload,
    execute_ecu_advance,
    execute_ecu_reset,
    list_ecus,
    list_memory_snapshots,
    observe_ecu_fault,
    replace_ecu_state,
    require_ecu,
    require_memory_snapshot,
    restore_memory_snapshot,
)
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.vehicles.models import Vehicle
from atep.vehicles.service import require_vehicle

router = APIRouter(prefix="/vehicles/{vehicle_id}/ecus", tags=["ecus"])
profiles_router = APIRouter(prefix="/ecu-profiles", tags=["ecu-profiles"])
ecus_read = require_permissions(PermissionName.ECUS_READ.value)
ecus_manage = require_permissions(PermissionName.ECUS_MANAGE.value)


def ecu_response(ecu: ElectronicControlUnit, vehicle: Vehicle) -> EcuResponse:
    return EcuResponse(
        id=ecu.id,
        vehicle_id=vehicle.identifier,
        identifier=ecu.identifier,
        display_name=ecu.display_name,
        ecu_type=ecu.ecu_type,
        version=ecu.version,
        simulation_time_ms=ecu.simulation_time_ms,
        boot_count=ecu.boot_count,
        profile_version=ecu.profile_version,
        created_at=ecu.created_at,
        updated_at=ecu.updated_at,
        **ecu_state_payload(ecu).model_dump(),
    )


@router.post("", response_model=EcuResponse, status_code=status.HTTP_201_CREATED)
async def create_ecu_endpoint(
    vehicle_id: str,
    command: EcuCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(ecus_manage)],
) -> EcuResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await create_ecu(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return ecu_response(ecu, vehicle)


def ecu_advance_response(
    command: EcuSimulationCommand, vehicle: Vehicle, ecu: ElectronicControlUnit, *, duplicate: bool
) -> EcuAdvanceResponse:
    return EcuAdvanceResponse(
        command_id=command.command_id,
        vehicle_id=vehicle.identifier,
        ecu_id=ecu.identifier,
        duration_ms=int(command.result["duration_ms"]),
        previous_version=command.previous_version,
        state_version=command.state_version,
        previous_time_ms=command.previous_time_ms,
        simulation_time_ms=command.simulation_time_ms,
        task_runs=[EcuTaskRunSummary.model_validate(item) for item in command.result["task_runs"]],
        profile_version=str(command.result["profile_version"]),
        behavior_state=dict(command.result["behavior_state"]),
        duplicate=duplicate,
        created_at=command.created_at,
    )


def ecu_reset_response(
    command: EcuSimulationCommand, vehicle: Vehicle, ecu: ElectronicControlUnit, *, duplicate: bool
) -> EcuResetResponse:
    return EcuResetResponse(
        command_id=command.command_id,
        vehicle_id=vehicle.identifier,
        ecu_id=ecu.identifier,
        mode=str(command.result["mode"]),
        reset_duration_ms=int(command.result["reset_duration_ms"]),
        previous_version=command.previous_version,
        state_version=command.state_version,
        previous_time_ms=command.previous_time_ms,
        simulation_time_ms=command.simulation_time_ms,
        boot_count=int(command.result["boot_count"]),
        memory_preserved=bool(command.result["memory_preserved"]),
        volatile_cells_reset=int(command.result["volatile_cells_reset"]),
        non_volatile_cells_preserved=int(
            command.result["non_volatile_cells_preserved"]
        ),
        faults_preserved=bool(command.result["faults_preserved"]),
        duplicate=duplicate,
        created_at=command.created_at,
    )


@router.post(
    "/{ecu_id}/simulation/advance",
    response_model=EcuAdvanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def advance_ecu_simulation_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: EcuAdvanceCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(ecus_manage)],
) -> EcuAdvanceResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await require_ecu(session, vehicle=vehicle, identifier=ecu_id)
    execution, duplicate = await execute_ecu_advance(
        session,
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(execution, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return ecu_advance_response(execution, vehicle, ecu, duplicate=duplicate)


@router.post(
    "/{ecu_id}/reset", response_model=EcuResetResponse, status_code=status.HTTP_201_CREATED
)
async def reset_ecu_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: EcuResetCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(ecus_manage)],
) -> EcuResetResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await require_ecu(session, vehicle=vehicle, identifier=ecu_id)
    execution, duplicate = await execute_ecu_reset(
        session,
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(execution, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return ecu_reset_response(execution, vehicle, ecu, duplicate=duplicate)


@router.get("", response_model=EcuPage)
async def list_ecus_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(ecus_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    ecu_type: EcuType | None = None,
) -> EcuPage:
    vehicle = await require_vehicle(session, vehicle_id)
    ecus, total = await list_ecus(
        session, vehicle=vehicle, limit=limit, offset=offset, ecu_type=ecu_type
    )
    return EcuPage(
        items=[ecu_response(ecu, vehicle) for ecu in ecus],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{ecu_id}", response_model=EcuResponse)
async def get_ecu_endpoint(
    vehicle_id: str,
    ecu_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(ecus_read)],
) -> EcuResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    return ecu_response(
        await require_ecu(session, vehicle=vehicle, identifier=ecu_id), vehicle
    )


@router.put("/{ecu_id}/state", response_model=EcuResponse)
async def replace_ecu_state_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: EcuStateReplace,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(ecus_manage)],
) -> EcuResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await require_ecu(session, vehicle=vehicle, identifier=ecu_id)
    ecu, duplicate = await replace_ecu_state(
        session,
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.headers["X-Idempotent-Replay"] = "true"
    return ecu_response(ecu, vehicle)


def profile_response(ecu_type: EcuType) -> EcuBehaviorProfileResponse:
    profile = behavior_profile(ecu_type)
    return EcuBehaviorProfileResponse(
        ecu_type=profile.ecu_type,
        profile_version=profile.profile_version,
        description=profile.description,
        tasks=[
            EcuProfileTaskResponse(
                **task.model_dump(), state_effect=profile.state_effects[task.task_id]
            )
            for task in profile.tasks
        ],
        initial_state=dict(profile.initial_state),
    )


@profiles_router.get("", response_model=list[EcuBehaviorProfileResponse])
async def list_ecu_profiles_endpoint(
    _: Annotated[User, Depends(ecus_read)],
) -> list[EcuBehaviorProfileResponse]:
    return [profile_response(profile.ecu_type) for profile in behavior_profiles()]


@profiles_router.get("/{ecu_type}", response_model=EcuBehaviorProfileResponse)
async def get_ecu_profile_endpoint(
    ecu_type: EcuType,
    _: Annotated[User, Depends(ecus_read)],
) -> EcuBehaviorProfileResponse:
    return profile_response(ecu_type)


def memory_snapshot_response(
    snapshot: EcuMemorySnapshot, vehicle: Vehicle, ecu: ElectronicControlUnit
) -> EcuMemorySnapshotResponse:
    return EcuMemorySnapshotResponse(
        id=snapshot.id,
        vehicle_id=vehicle.identifier,
        ecu_id=ecu.identifier,
        name=snapshot.name,
        state_version=snapshot.state_version,
        simulation_time_ms=snapshot.simulation_time_ms,
        memory_cell_count=len(snapshot.memory),
        checksum_sha256=snapshot.checksum_sha256,
        created_at=snapshot.created_at,
    )


@router.post(
    "/{ecu_id}/memory/snapshots",
    response_model=EcuMemorySnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_memory_snapshot_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: EcuSnapshotCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(ecus_manage)],
) -> EcuMemorySnapshotResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await require_ecu(session, vehicle=vehicle, identifier=ecu_id)
    snapshot = await create_memory_snapshot(
        session,
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return memory_snapshot_response(snapshot, vehicle, ecu)


@router.get("/{ecu_id}/memory/snapshots", response_model=EcuMemorySnapshotPage)
async def list_memory_snapshots_endpoint(
    vehicle_id: str,
    ecu_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(ecus_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> EcuMemorySnapshotPage:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await require_ecu(session, vehicle=vehicle, identifier=ecu_id)
    snapshots, total = await list_memory_snapshots(
        session, ecu=ecu, limit=limit, offset=offset
    )
    return EcuMemorySnapshotPage(
        items=[memory_snapshot_response(item, vehicle, ecu) for item in snapshots],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{ecu_id}/memory/snapshots/{snapshot_id}/restore", response_model=EcuResponse
)
async def restore_memory_snapshot_endpoint(
    vehicle_id: str,
    ecu_id: str,
    snapshot_id: UUID,
    command: EcuSnapshotRestoreCommand,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(ecus_manage)],
) -> EcuResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await require_ecu(session, vehicle=vehicle, identifier=ecu_id)
    snapshot = await require_memory_snapshot(session, ecu=ecu, snapshot_id=snapshot_id)
    ecu = await restore_memory_snapshot(
        session,
        vehicle=vehicle,
        ecu=ecu,
        snapshot=snapshot,
        expected_version=command.expected_version,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return ecu_response(ecu, vehicle)


@router.post(
    "/{ecu_id}/memory/corrupt",
    response_model=EcuMemoryCorruptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def corrupt_ecu_memory_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: EcuMemoryCorruptionCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(ecus_manage)],
) -> EcuMemoryCorruptionResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await require_ecu(session, vehicle=vehicle, identifier=ecu_id)
    execution, duplicate = await corrupt_ecu_memory(
        session,
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(execution, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return EcuMemoryCorruptionResponse(
        command_id=execution.command_id,
        vehicle_id=vehicle.identifier,
        ecu_id=ecu.identifier,
        seed=int(execution.result["seed"]),
        requested_bit_flips=int(execution.result["requested_bit_flips"]),
        changes=[EcuMemoryChange.model_validate(item) for item in execution.result["changes"]],
        previous_version=execution.previous_version,
        state_version=execution.state_version,
        duplicate=duplicate,
        created_at=execution.created_at,
    )


def fault_lifecycle_response(
    execution: EcuSimulationCommand,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    *,
    duplicate: bool,
) -> EcuFaultLifecycleResponse:
    return EcuFaultLifecycleResponse(
        command_id=execution.command_id,
        vehicle_id=vehicle.identifier,
        ecu_id=ecu.identifier,
        transition=str(execution.result["transition"]),
        fault=EcuFault.model_validate(execution.result["fault"]),
        previous_version=execution.previous_version,
        state_version=execution.state_version,
        duplicate=duplicate,
        created_at=execution.created_at,
    )


@router.post(
    "/{ecu_id}/faults/observe",
    response_model=EcuFaultLifecycleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def observe_ecu_fault_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: EcuFaultObservationCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(ecus_manage)],
) -> EcuFaultLifecycleResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await require_ecu(session, vehicle=vehicle, identifier=ecu_id)
    execution, duplicate = await observe_ecu_fault(
        session,
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(execution, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return fault_lifecycle_response(execution, vehicle, ecu, duplicate=duplicate)


@router.post(
    "/{ecu_id}/faults/{fault_code}/clear",
    response_model=EcuFaultLifecycleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def clear_ecu_fault_endpoint(
    vehicle_id: str,
    ecu_id: str,
    fault_code: str,
    command: EcuFaultClearCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(ecus_manage)],
) -> EcuFaultLifecycleResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await require_ecu(session, vehicle=vehicle, identifier=ecu_id)
    canonical_code = EcuFault(code=fault_code, severity="info").code
    execution, duplicate = await clear_ecu_fault(
        session,
        vehicle=vehicle,
        ecu=ecu,
        fault_code=canonical_code,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(execution, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return fault_lifecycle_response(execution, vehicle, ecu, duplicate=duplicate)


@router.get("/{ecu_id}/faults/dtc-candidates", response_model=EcuDtcCandidatePage)
async def list_ecu_dtc_candidates_endpoint(
    vehicle_id: str,
    ecu_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(ecus_read)],
) -> EcuDtcCandidatePage:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await require_ecu(session, vehicle=vehicle, identifier=ecu_id)
    items = dtc_candidates(ecu)
    return EcuDtcCandidatePage(items=items, total=len(items))
