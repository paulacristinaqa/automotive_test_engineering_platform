from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.can_network.models import CanFrameTransmission, CanNetwork
from atep.can_network.schemas import (
    CanFrameSubmitCommand,
    CanFrameTransmissionPage,
    CanFrameTransmissionResponse,
    CanNetworkCreate,
    CanNetworkResponse,
)
from atep.can_network.service import (
    create_can_network,
    list_transmissions,
    require_can_network,
    submit_can_frame,
)
from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.vehicles.models import Vehicle
from atep.vehicles.service import require_vehicle

router = APIRouter(prefix="/vehicles/{vehicle_id}/can-networks", tags=["can-networks"])
can_read = require_permissions(PermissionName.CAN_NETWORKS_READ.value)
can_manage = require_permissions(PermissionName.CAN_NETWORKS_MANAGE.value)


def network_response(network: CanNetwork, vehicle: Vehicle) -> CanNetworkResponse:
    return CanNetworkResponse(
        id=network.id,
        vehicle_id=vehicle.identifier,
        identifier=network.identifier,
        display_name=network.display_name,
        bitrate_kbps=network.bitrate_kbps,
        nodes=network.nodes,
        frame_contracts=network.frame_contracts,
        version=network.version,
        simulation_time_us=network.simulation_time_us,
        next_sequence=network.next_sequence,
        created_at=network.created_at,
        updated_at=network.updated_at,
    )


def transmission_response(
    item: CanFrameTransmission, network: CanNetwork, vehicle: Vehicle, *, duplicate: bool = False
) -> CanFrameTransmissionResponse:
    return CanFrameTransmissionResponse(
        command_id=item.command_id,
        vehicle_id=vehicle.identifier,
        network_id=network.identifier,
        contract_id=item.contract_id,
        producer_node_id=item.producer_node_id,
        frame_id=item.frame_id,
        frame_format=item.frame_format,
        payload=item.payload,
        sequence=item.sequence,
        transmission_time_us=item.transmission_time_us,
        previous_version=item.previous_version,
        network_version=item.network_version,
        duplicate=duplicate,
        created_at=item.created_at,
    )


@router.post("", response_model=CanNetworkResponse, status_code=status.HTTP_201_CREATED)
async def create_network_endpoint(
    vehicle_id: str,
    command: CanNetworkCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(can_manage)],
) -> CanNetworkResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    network = await create_can_network(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return network_response(network, vehicle)


@router.get("", response_model=CanNetworkResponse)
async def get_network_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(can_read)],
) -> CanNetworkResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    return network_response(await require_can_network(session, vehicle=vehicle), vehicle)


@router.post(
    "/frames", response_model=CanFrameTransmissionResponse, status_code=status.HTTP_201_CREATED
)
async def submit_frame_endpoint(
    vehicle_id: str,
    command: CanFrameSubmitCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(can_manage)],
) -> CanFrameTransmissionResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    item, network, duplicate = await submit_can_frame(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(item, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return transmission_response(item, network, vehicle, duplicate=duplicate)


@router.get("/frames", response_model=CanFrameTransmissionPage)
async def list_frames_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(can_read)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> CanFrameTransmissionPage:
    vehicle = await require_vehicle(session, vehicle_id)
    network = await require_can_network(session, vehicle=vehicle)
    items, total = await list_transmissions(session, network=network, limit=limit, offset=offset)
    return CanFrameTransmissionPage(
        items=[transmission_response(item, network, vehicle) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
