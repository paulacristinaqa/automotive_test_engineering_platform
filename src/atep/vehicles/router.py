from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.registry.service import authenticate_module
from atep.registry.workload_identity import ModuleAuthentication, module_authentication
from atep.vehicles.models import (
    Vehicle,
    VehicleCommand,
    VehicleDigitalState,
    VehicleSimulationStep,
    VehicleSimulationTransition,
    VehicleTelemetryEvent,
)
from atep.vehicles.schemas import (
    PROPERTY_NAME_PATTERN,
    DigitalVehicleStateReplace,
    DigitalVehicleStateResponse,
    TelemetryIngest,
    TelemetryPage,
    TelemetryResponse,
    VehicleActuatorInputs,
    VehicleCommandAcknowledge,
    VehicleCommandClaim,
    VehicleCommandCreate,
    VehicleCommandDelivery,
    VehicleCommandPage,
    VehicleCommandParameters,
    VehicleCommandResponse,
    VehicleCommandStatus,
    VehicleCreate,
    VehiclePage,
    VehicleResponse,
    VehicleSensorConfiguration,
    VehicleSensorReadings,
    VehicleSimulationStepCommand,
    VehicleSimulationStepResponse,
    VehicleSimulationTransitionCommand,
    VehicleSimulationTransitionResponse,
    VehicleStatus,
    VehicleStatusUpdate,
)
from atep.vehicles.service import (
    COMMAND_CONSUME_CAPABILITY,
    acknowledge_vehicle_command,
    claim_next_vehicle_command,
    create_vehicle,
    create_vehicle_command,
    digital_state_payload,
    execute_vehicle_simulation_step,
    execute_vehicle_simulation_transition,
    ingest_telemetry,
    list_telemetry,
    list_vehicle_commands,
    list_vehicles,
    replace_vehicle_digital_state,
    require_vehicle,
    require_vehicle_digital_state,
    update_vehicle_status,
)

TELEMETRY_PUBLISH_CAPABILITY = "vehicle.telemetry.publish"

router = APIRouter(prefix="/vehicles", tags=["vehicles"])
vehicles_read = require_permissions(PermissionName.VEHICLES_READ.value)
vehicles_manage = require_permissions(PermissionName.VEHICLES_MANAGE.value)
telemetry_read = require_permissions(PermissionName.TELEMETRY_READ.value)
vehicle_commands_read = require_permissions(PermissionName.VEHICLE_COMMANDS_READ.value)
vehicle_commands_write = require_permissions(PermissionName.VEHICLE_COMMANDS_WRITE.value)
digital_vehicle_read = require_permissions(PermissionName.DIGITAL_VEHICLE_READ.value)
digital_vehicle_write = require_permissions(PermissionName.DIGITAL_VEHICLE_WRITE.value)


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


def command_response(command: VehicleCommand, vehicle: Vehicle) -> VehicleCommandResponse:
    return VehicleCommandResponse(
        id=command.id,
        command_id=command.command_id,
        vehicle_id=vehicle.identifier,
        target_module_id=command.target_module_id,
        requested_by_user_id=command.requested_by_user_id,
        test_run_id=command.test_run_id,
        kind=command.kind,
        parameters=VehicleCommandParameters.model_validate(command.payload),
        status=command.status,
        attempt_count=command.attempt_count,
        available_at=command.available_at,
        leased_until=command.leased_until,
        completed_at=command.completed_at,
        result=command.result,
        error_code=command.error_code,
        error_message=command.error_message,
        created_at=command.created_at,
        updated_at=command.updated_at,
    )


def digital_vehicle_state_response(
    state: VehicleDigitalState, vehicle: Vehicle
) -> DigitalVehicleStateResponse:
    return DigitalVehicleStateResponse(
        vehicle_id=vehicle.identifier,
        version=state.version,
        simulation_time_ms=state.simulation_time_ms,
        updated_at=state.updated_at,
        **digital_state_payload(state).model_dump(),
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


@router.get("/{vehicle_id}/state", response_model=DigitalVehicleStateResponse)
async def get_digital_vehicle_state_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(digital_vehicle_read)],
) -> DigitalVehicleStateResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    state = await require_vehicle_digital_state(session, vehicle=vehicle)
    return digital_vehicle_state_response(state, vehicle)


def simulation_transition_response(
    transition: VehicleSimulationTransition, vehicle: Vehicle, *, duplicate: bool = False
) -> VehicleSimulationTransitionResponse:
    return VehicleSimulationTransitionResponse(
        command_id=transition.command_id,
        vehicle_id=vehicle.identifier,
        from_mode=transition.from_mode,
        to_mode=transition.to_mode,
        duration_ms=transition.duration_ms,
        previous_state_version=transition.previous_state_version,
        state_version=transition.state_version,
        simulation_time_ms=transition.simulation_time_ms,
        duplicate=duplicate,
        created_at=transition.created_at,
    )


def simulation_step_response(
    step: VehicleSimulationStep, vehicle: Vehicle, *, duplicate: bool = False
) -> VehicleSimulationStepResponse:
    return VehicleSimulationStepResponse(
        command_id=step.command_id,
        vehicle_id=vehicle.identifier,
        duration_ms=step.duration_ms,
        seed=step.seed,
        inputs=VehicleActuatorInputs.model_validate(step.inputs),
        sensors=VehicleSensorConfiguration.model_validate(step.sensor_configuration),
        readings=VehicleSensorReadings.model_validate(step.sensor_readings),
        previous_state_version=step.previous_state_version,
        state_version=step.state_version,
        simulation_time_ms=step.simulation_time_ms,
        duplicate=duplicate,
        created_at=step.created_at,
    )


@router.post(
    "/{vehicle_id}/simulation/transitions",
    response_model=VehicleSimulationTransitionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def execute_simulation_transition_endpoint(
    vehicle_id: str,
    command: VehicleSimulationTransitionCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(digital_vehicle_write)],
) -> VehicleSimulationTransitionResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    transition, duplicate = await execute_vehicle_simulation_transition(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(transition, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return simulation_transition_response(transition, vehicle, duplicate=duplicate)


@router.post(
    "/{vehicle_id}/simulation/steps",
    response_model=VehicleSimulationStepResponse,
    status_code=status.HTTP_201_CREATED,
)
async def execute_simulation_step_endpoint(
    vehicle_id: str,
    command: VehicleSimulationStepCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(digital_vehicle_write)],
) -> VehicleSimulationStepResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    step, duplicate = await execute_vehicle_simulation_step(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(step, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return simulation_step_response(step, vehicle, duplicate=duplicate)


@router.put("/{vehicle_id}/state", response_model=DigitalVehicleStateResponse)
async def replace_digital_vehicle_state_endpoint(
    vehicle_id: str,
    command: DigitalVehicleStateReplace,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(digital_vehicle_write)],
) -> DigitalVehicleStateResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    state, _ = await replace_vehicle_digital_state(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return digital_vehicle_state_response(state, vehicle)


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
    authentication: Annotated[ModuleAuthentication, Depends(module_authentication)],
) -> TelemetryResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    module = await authenticate_module(
        session,
        module_id=module_id,
        token=authentication.token,
        spiffe_module_name=authentication.spiffe_module_name,
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


@router.post(
    "/{vehicle_id}/commands",
    response_model=VehicleCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_vehicle_command_endpoint(
    vehicle_id: str,
    request: Request,
    response: Response,
    command: VehicleCommandCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(vehicle_commands_write)],
) -> VehicleCommandResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    queued, duplicate = await create_vehicle_command(
        session,
        vehicle=vehicle,
        actor_user_id=actor.id,
        command=command,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return command_response(queued, vehicle)


@router.get("/{vehicle_id}/commands", response_model=VehicleCommandPage)
async def list_vehicle_commands_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(vehicle_commands_read)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[VehicleCommandStatus | None, Query(alias="status")] = None,
) -> VehicleCommandPage:
    vehicle = await require_vehicle(session, vehicle_id)
    commands, total = await list_vehicle_commands(
        session,
        vehicle=vehicle,
        limit=limit,
        offset=offset,
        status=status_filter,
    )
    return VehicleCommandPage(
        items=[command_response(item, vehicle) for item in commands],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{vehicle_id}/commands/claim",
    response_model=VehicleCommandDelivery,
    responses={status.HTTP_204_NO_CONTENT: {"description": "No command is available."}},
)
async def claim_vehicle_command_endpoint(
    vehicle_id: str,
    claim: VehicleCommandClaim,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    module_id: Annotated[UUID, Header(alias="X-ATEP-Module-ID")],
    authentication: Annotated[ModuleAuthentication, Depends(module_authentication)],
) -> VehicleCommandDelivery | Response:
    vehicle = await require_vehicle(session, vehicle_id)
    module = await authenticate_module(
        session,
        module_id=module_id,
        token=authentication.token,
        spiffe_module_name=authentication.spiffe_module_name,
        required_capability=COMMAND_CONSUME_CAPABILITY,
    )
    command, claim_token = await claim_next_vehicle_command(
        session,
        vehicle=vehicle,
        module=module,
        lease_seconds=claim.lease_seconds,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if command is None or claim_token is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return VehicleCommandDelivery(
        **command_response(command, vehicle).model_dump(), claim_token=claim_token
    )


@router.post(
    "/{vehicle_id}/commands/{command_id}/acknowledgement",
    response_model=VehicleCommandResponse,
)
async def acknowledge_vehicle_command_endpoint(
    vehicle_id: str,
    acknowledgement: VehicleCommandAcknowledge,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    module_id: Annotated[UUID, Header(alias="X-ATEP-Module-ID")],
    authentication: Annotated[ModuleAuthentication, Depends(module_authentication)],
    command_id: Annotated[
        str,
        Path(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$"),
    ],
) -> VehicleCommandResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    module = await authenticate_module(
        session,
        module_id=module_id,
        token=authentication.token,
        spiffe_module_name=authentication.spiffe_module_name,
        required_capability=COMMAND_CONSUME_CAPABILITY,
    )
    command, _ = await acknowledge_vehicle_command(
        session,
        vehicle=vehicle,
        module=module,
        command_id=command_id,
        acknowledgement=acknowledgement,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return command_response(command, vehicle)
