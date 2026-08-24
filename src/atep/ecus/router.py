from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.ecus.models import EcuSimulationCommand, ElectronicControlUnit
from atep.ecus.profiles import behavior_profile, behavior_profiles
from atep.ecus.schemas import (
    EcuAdvanceCommand,
    EcuAdvanceResponse,
    EcuBehaviorProfileResponse,
    EcuCreate,
    EcuPage,
    EcuProfileTaskResponse,
    EcuResetCommand,
    EcuResetResponse,
    EcuResponse,
    EcuStateReplace,
    EcuTaskRunSummary,
    EcuType,
)
from atep.ecus.service import (
    create_ecu,
    ecu_state_payload,
    execute_ecu_advance,
    execute_ecu_reset,
    list_ecus,
    replace_ecu_state,
    require_ecu,
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
