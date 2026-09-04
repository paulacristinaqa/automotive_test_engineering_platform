from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.electric_vehicle.schemas import (
    BatteryPackCreate,
    BatteryPackResponse,
    BatterySimulationCommand,
    BrakeSimulationCommand,
    MotorInverterCreate,
    MotorInverterResponse,
    MotorSimulationCommand,
    RegenerativeBrakeCreate,
    RegenerativeBrakeResponse,
)
from atep.electric_vehicle.service import (
    battery_response,
    create_battery_pack,
    create_motor_inverter,
    create_regenerative_brake,
    motor_inverter_response,
    regenerative_brake_response,
    require_battery_pack,
    require_motor_inverter,
    require_regenerative_brake,
    simulate_battery_step,
    simulate_brake_step,
    simulate_motor_step,
)
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.vehicles.service import require_vehicle

router = APIRouter(prefix="/vehicles/{vehicle_id}/electric", tags=["electric-vehicle"])
electric_vehicle_read = require_permissions(PermissionName.ELECTRIC_VEHICLE_READ.value)
electric_vehicle_manage = require_permissions(PermissionName.ELECTRIC_VEHICLE_MANAGE.value)


@router.post("/battery", response_model=BatteryPackResponse, status_code=status.HTTP_201_CREATED)
async def create_battery_pack_endpoint(
    vehicle_id: str,
    command: BatteryPackCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(electric_vehicle_manage)],
) -> BatteryPackResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    pack = await create_battery_pack(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(pack, attribute_names=["created_at", "updated_at"])
    return battery_response(pack, vehicle)


@router.get("/battery", response_model=BatteryPackResponse)
async def get_battery_pack_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(electric_vehicle_read)],
) -> BatteryPackResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    return battery_response(await require_battery_pack(session, vehicle=vehicle), vehicle)


@router.post(
    "/battery/steps", response_model=BatteryPackResponse, status_code=status.HTTP_201_CREATED
)
async def simulate_battery_step_endpoint(
    vehicle_id: str,
    command: BatterySimulationCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(electric_vehicle_manage)],
) -> BatteryPackResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    result, duplicate = await simulate_battery_step(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return result


@router.post(
    "/powertrain", response_model=MotorInverterResponse, status_code=status.HTTP_201_CREATED
)
async def create_motor_inverter_endpoint(
    vehicle_id: str,
    command: MotorInverterCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(electric_vehicle_manage)],
) -> MotorInverterResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    pack = await require_battery_pack(session, vehicle=vehicle)
    state = await create_motor_inverter(
        session,
        vehicle=vehicle,
        pack=pack,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(state, attribute_names=["created_at", "updated_at"])
    return motor_inverter_response(state, vehicle, pack)


@router.get("/powertrain", response_model=MotorInverterResponse)
async def get_motor_inverter_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(electric_vehicle_read)],
) -> MotorInverterResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    pack = await require_battery_pack(session, vehicle=vehicle)
    state = await require_motor_inverter(session, vehicle=vehicle)
    return motor_inverter_response(state, vehicle, pack)


@router.post(
    "/powertrain/steps", response_model=MotorInverterResponse, status_code=status.HTTP_201_CREATED
)
async def simulate_motor_step_endpoint(
    vehicle_id: str,
    command: MotorSimulationCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(electric_vehicle_manage)],
) -> MotorInverterResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    result, duplicate = await simulate_motor_step(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return result


@router.post(
    "/braking", response_model=RegenerativeBrakeResponse, status_code=status.HTTP_201_CREATED
)
async def create_regenerative_brake_endpoint(
    vehicle_id: str,
    command: RegenerativeBrakeCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(electric_vehicle_manage)],
) -> RegenerativeBrakeResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    pack = await require_battery_pack(session, vehicle=vehicle)
    motor = await require_motor_inverter(session, vehicle=vehicle)
    state = await create_regenerative_brake(
        session,
        vehicle=vehicle,
        pack=pack,
        motor=motor,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(state, attribute_names=["created_at", "updated_at"])
    return regenerative_brake_response(state, vehicle, pack)


@router.get("/braking", response_model=RegenerativeBrakeResponse)
async def get_regenerative_brake_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(electric_vehicle_read)],
) -> RegenerativeBrakeResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    pack = await require_battery_pack(session, vehicle=vehicle)
    state = await require_regenerative_brake(session, vehicle=vehicle)
    return regenerative_brake_response(state, vehicle, pack)


@router.post(
    "/braking/steps",
    response_model=RegenerativeBrakeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def simulate_brake_step_endpoint(
    vehicle_id: str,
    command: BrakeSimulationCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(electric_vehicle_manage)],
) -> RegenerativeBrakeResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    result, duplicate = await simulate_brake_step(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return result
