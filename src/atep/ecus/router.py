from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.ecus.models import ElectronicControlUnit
from atep.ecus.schemas import EcuCreate, EcuPage, EcuResponse, EcuStateReplace, EcuType
from atep.ecus.service import (
    create_ecu,
    ecu_state_payload,
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
