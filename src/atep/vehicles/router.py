from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.registry.service import authenticate_module
from atep.vehicles.models import Vehicle, VehicleTelemetryEvent
from atep.vehicles.schemas import (
    PROPERTY_NAME_PATTERN,
    TelemetryIngest,
    TelemetryPage,
    TelemetryResponse,
    VehicleCreate,
    VehiclePage,
    VehicleResponse,
    VehicleStatus,
    VehicleStatusUpdate,
)
from atep.vehicles.service import (
    create_vehicle,
    ingest_telemetry,
    list_telemetry,
    list_vehicles,
    require_vehicle,
    update_vehicle_status,
)

TELEMETRY_PUBLISH_CAPABILITY = "vehicle.telemetry.publish"

router = APIRouter(prefix="/vehicles", tags=["vehicles"])
vehicles_read = require_permissions(PermissionName.VEHICLES_READ.value)
vehicles_manage = require_permissions(PermissionName.VEHICLES_MANAGE.value)
telemetry_read = require_permissions(PermissionName.TELEMETRY_READ.value)


def vehicle_response(vehicle: Vehicle) -> VehicleResponse:
    return VehicleResponse(
        id=vehicle.id,
        identifier=vehicle.identifier,
        display_name=vehicle.display_name,
        model=vehicle.model,
        description=vehicle.description,
        status=VehicleStatus(vehicle.status),
        created_at=vehicle.created_at,
        updated_at=vehicle.updated_at,
    )


def telemetry_response(
    event: VehicleTelemetryEvent, vehicle: Vehicle, *, duplicate: bool = False
) -> TelemetryResponse:
    return TelemetryResponse(
        id=event.id,
        event_id=event.event_id,
        vehicle_id=vehicle.identifier,
        source_module_id=event.source_module_id,
        source=event.source,
        property=event.property_name,
        value=event.value,
        unit=event.unit,
        timestamp=event.observed_at,
        received_at=event.created_at,
        duplicate=duplicate,
    )


@router.post("", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle_endpoint(
    command: VehicleCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(vehicles_manage)],
) -> VehicleResponse:
    vehicle = await create_vehicle(
        session,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return vehicle_response(vehicle)


@router.get("", response_model=VehiclePage)
async def list_vehicles_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(vehicles_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[VehicleStatus | None, Query(alias="status")] = None,
) -> VehiclePage:
    vehicles, total = await list_vehicles(session, limit=limit, offset=offset, status=status_filter)
    return VehiclePage(
        items=[vehicle_response(item) for item in vehicles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(vehicles_read)],
) -> VehicleResponse:
    return vehicle_response(await require_vehicle(session, vehicle_id))


@router.patch("/{vehicle_id}/status", response_model=VehicleResponse)
async def update_vehicle_status_endpoint(
    vehicle_id: str,
    command: VehicleStatusUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(vehicles_manage)],
) -> VehicleResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    await update_vehicle_status(
        session,
        vehicle=vehicle,
        status=command.status,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return vehicle_response(vehicle)


@router.post(
    "/{vehicle_id}/telemetry",
    response_model=TelemetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_telemetry_endpoint(
    vehicle_id: str,
    command: TelemetryIngest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    module_id: Annotated[UUID, Header(alias="X-ATEP-Module-ID")],
    module_token: Annotated[str, Header(alias="X-ATEP-Module-Token", min_length=32)],
) -> TelemetryResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    module = await authenticate_module(
        session,
        module_id=module_id,
        token=module_token,
        required_capability=TELEMETRY_PUBLISH_CAPABILITY,
    )
    event, duplicate = await ingest_telemetry(
        session,
        vehicle=vehicle,
        module=module,
        command=command,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return telemetry_response(event, vehicle, duplicate=duplicate)


@router.get("/{vehicle_id}/telemetry", response_model=TelemetryPage)
async def list_telemetry_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(telemetry_read)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    property_filter: Annotated[
        str | None,
        Query(
            alias="property",
            min_length=1,
            max_length=120,
            pattern=PROPERTY_NAME_PATTERN.pattern,
        ),
    ] = None,
) -> TelemetryPage:
    vehicle = await require_vehicle(session, vehicle_id)
    events, total = await list_telemetry(
        session,
        vehicle=vehicle,
        limit=limit,
        offset=offset,
        property_name=property_filter,
    )
    return TelemetryPage(
        items=[telemetry_response(item, vehicle) for item in events],
        total=total,
        limit=limit,
        offset=offset,
    )
