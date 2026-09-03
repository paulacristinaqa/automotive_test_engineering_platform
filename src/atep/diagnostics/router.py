from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.errors import DiagnosticContractError
from atep.db.session import get_session
from atep.diagnostics.models import (
    DiagnosticCampaign,
    DiagnosticCommand,
    DiagnosticDataIdentifier,
    DiagnosticFlashState,
    DiagnosticRoutine,
    DiagnosticRoutineState,
    DiagnosticSecurityState,
    DiagnosticSessionState,
    DiagnosticTroubleCode,
)
from atep.diagnostics.schemas import (
    DiagnosticCampaignCommand,
    DiagnosticCampaignResponse,
    DiagnosticCommandResponse,
    DiagnosticEcuResetCommand,
    DiagnosticSessionControlCommand,
    DiagnosticSessionResponse,
    DidCreate,
    DidPage,
    DidReadCommand,
    DidResponse,
    DidWriteCommand,
    DtcClearCommand,
    DtcPage,
    DtcReportCommand,
    DtcResponse,
    FlashRequestDownloadCommand,
    FlashStateResponse,
    FlashTransferDataCommand,
    FlashTransferExitCommand,
    ObdMode01Request,
    ObdMode01Response,
    ObdMode03Response,
    ObdPidValue,
    RoutineControlCommand,
    RoutineCreate,
    RoutinePage,
    RoutineResponse,
    SecurityAccessCommand,
    SecurityAccessStateResponse,
)
from atep.diagnostics.service import (
    clear_dtcs,
    control_routine,
    control_session,
    create_did,
    create_routine,
    execute_diagnostic_campaign,
    get_or_create_flash_state,
    get_or_create_security_state,
    get_or_create_session,
    list_dids,
    list_dtcs,
    list_routines,
    read_dids,
    read_obd_mode_01,
    report_dtc,
    request_download,
    request_transfer_exit,
    require_diagnostic_campaign,
    require_did,
    require_dtc,
    require_routine,
    reset_ecu,
    security_access,
    transfer_data,
    write_did,
)
from atep.ecus.models import ElectronicControlUnit
from atep.ecus.service import require_ecu
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.vehicles.models import Vehicle
from atep.vehicles.service import require_vehicle

router = APIRouter(prefix="/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics", tags=["diagnostics"])
diagnostics_read = require_permissions(PermissionName.DIAGNOSTICS_READ.value)
diagnostics_manage = require_permissions(PermissionName.DIAGNOSTICS_MANAGE.value)


async def _context(
    session: AsyncSession, *, vehicle_id: str, ecu_id: str
) -> tuple[Vehicle, ElectronicControlUnit]:
    vehicle = await require_vehicle(session, vehicle_id)
    ecu = await require_ecu(session, vehicle=vehicle, identifier=ecu_id)
    return vehicle, ecu


def command_response(
    execution: DiagnosticCommand, ecu: ElectronicControlUnit, *, duplicate: bool
) -> DiagnosticCommandResponse:
    return DiagnosticCommandResponse(
        command_id=execution.command_id,
        ecu_id=ecu.identifier,
        service_id=execution.service_id,
        positive_response_service_id=execution.service_id + 0x40,
        previous_version=execution.previous_version,
        session_version=execution.session_version,
        result=execution.result,
        duplicate=duplicate,
        created_at=execution.created_at,
    )


def dtc_response(dtc: DiagnosticTroubleCode, ecu: ElectronicControlUnit) -> DtcResponse:
    return DtcResponse(
        id=dtc.id,
        ecu_id=ecu.identifier,
        code=dtc.code,
        status_mask=dtc.status_mask,
        severity=dtc.severity,
        description=dtc.description,
        occurrence_count=dtc.occurrence_count,
        first_seen_ms=dtc.first_seen_ms,
        last_seen_ms=dtc.last_seen_ms,
        snapshot=dtc.snapshot,
        version=dtc.version,
        created_at=dtc.created_at,
        updated_at=dtc.updated_at,
    )


def did_response(did: DiagnosticDataIdentifier, ecu: ElectronicControlUnit) -> DidResponse:
    return DidResponse(
        id=did.id,
        ecu_id=ecu.identifier,
        identifier=did.identifier,
        identifier_hex=f"0x{did.identifier:04X}",
        name=did.name,
        description=did.description,
        data_type=did.data_type,
        unit=did.unit,
        writable=did.writable,
        readable_sessions=did.readable_sessions,
        writable_sessions=did.writable_sessions,
        value=did.value,
        minimum=did.minimum,
        maximum=did.maximum,
        max_length=did.max_length,
        version=did.version,
        created_at=did.created_at,
        updated_at=did.updated_at,
    )


def routine_response(
    routine: DiagnosticRoutine,
    state: DiagnosticRoutineState,
    ecu: ElectronicControlUnit,
) -> RoutineResponse:
    return RoutineResponse(
        id=routine.id,
        ecu_id=ecu.identifier,
        identifier=routine.identifier,
        identifier_hex=f"0x{routine.identifier:04X}",
        name=routine.name,
        description=routine.description,
        allowed_sessions=routine.allowed_sessions,
        execution_time_ms=routine.execution_time_ms,
        supports_stop=routine.supports_stop,
        definition_version=routine.version,
        status=state.status,
        invocation_count=state.invocation_count,
        started_at_ms=state.started_at_ms,
        completes_at_ms=state.completes_at_ms,
        stopped_at_ms=state.stopped_at_ms,
        routine_version=state.version,
        created_at=routine.created_at,
        updated_at=state.updated_at,
    )


def security_state_response(
    security_state: DiagnosticSecurityState,
    diagnostic_state: DiagnosticSessionState,
    ecu: ElectronicControlUnit,
) -> SecurityAccessStateResponse:
    return SecurityAccessStateResponse(
        ecu_id=ecu.identifier,
        security_level=diagnostic_state.security_level,
        failed_attempts=security_state.failed_attempts,
        locked_until_ms=security_state.locked_until_ms,
        challenge_active=(
            security_state.expected_key_digest is not None
            and security_state.seed_expires_at_ms is not None
            and ecu.simulation_time_ms <= security_state.seed_expires_at_ms
        ),
        seed_expires_at_ms=security_state.seed_expires_at_ms,
        security_version=security_state.version,
        session_version=diagnostic_state.version,
        simulation_time_ms=ecu.simulation_time_ms,
    )


def flash_state_response(
    transfer: DiagnosticFlashState, ecu: ElectronicControlUnit
) -> FlashStateResponse:
    return FlashStateResponse(
        ecu_id=ecu.identifier,
        status=transfer.status,
        memory_address=transfer.memory_address,
        memory_size=transfer.memory_size,
        firmware_version=transfer.firmware_version,
        max_block_length=transfer.max_block_length,
        next_block_sequence_counter=transfer.next_block_sequence_counter,
        bytes_received=transfer.bytes_received,
        image_sha256=transfer.image_sha256,
        transfer_version=transfer.version,
    )


def campaign_response(
    campaign: DiagnosticCampaign, ecu: ElectronicControlUnit, *, duplicate: bool
) -> DiagnosticCampaignResponse:
    return DiagnosticCampaignResponse(
        command_id=campaign.command_id,
        ecu_id=ecu.identifier,
        name=campaign.name,
        transport=campaign.transport,
        doip=campaign.doip_envelope,
        status=campaign.status,
        step_count=len(campaign.results),
        results=campaign.results,
        duplicate=duplicate,
        created_at=campaign.created_at,
    )


@router.post("/obd/mode-01", response_model=ObdMode01Response)
async def read_obd_current_data_endpoint(
    vehicle_id: str,
    ecu_id: str,
    payload: ObdMode01Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(diagnostics_read)],
) -> ObdMode01Response:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    values = await read_obd_mode_01(session, ecu=ecu, request=payload)
    return ObdMode01Response(
        ecu_id=ecu.identifier,
        values=[ObdPidValue.model_validate(value) for value in values],
    )


@router.get("/obd/mode-03", response_model=ObdMode03Response)
async def read_obd_stored_dtcs_endpoint(
    vehicle_id: str,
    ecu_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(diagnostics_read)],
) -> ObdMode03Response:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    dtcs, _total = await list_dtcs(session, ecu=ecu, limit=200, offset=0, status_mask=None)
    return ObdMode03Response(ecu_id=ecu.identifier, dtcs=[dtc_response(dtc, ecu) for dtc in dtcs])


@router.post(
    "/campaigns", response_model=DiagnosticCampaignResponse, status_code=status.HTTP_201_CREATED
)
async def execute_diagnostic_campaign_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: DiagnosticCampaignCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DiagnosticCampaignResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    campaign, duplicate = await execute_diagnostic_campaign(
        session,
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(campaign, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
        response.headers["X-Idempotent-Replay"] = "true"
    return campaign_response(campaign, ecu, duplicate=duplicate)


@router.get("/campaigns/{command_id}", response_model=DiagnosticCampaignResponse)
async def get_diagnostic_campaign_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command_id: Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(diagnostics_read)],
) -> DiagnosticCampaignResponse:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    campaign = await require_diagnostic_campaign(session, ecu=ecu, command_id=command_id)
    return campaign_response(campaign, ecu, duplicate=False)


@router.get("/flash/state", response_model=FlashStateResponse)
async def get_flash_state_endpoint(
    vehicle_id: str,
    ecu_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(diagnostics_read)],
) -> FlashStateResponse:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    transfer = await get_or_create_flash_state(session, ecu=ecu)
    await session.commit()
    return flash_state_response(transfer, ecu)


@router.post(
    "/flash/request-download",
    response_model=DiagnosticCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_download_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: FlashRequestDownloadCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DiagnosticCommandResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    execution, duplicate = await request_download(
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
        response.headers["X-Idempotent-Replay"] = "true"
    return command_response(execution, ecu, duplicate=duplicate)


@router.post(
    "/flash/transfer-data",
    response_model=DiagnosticCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def transfer_data_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: FlashTransferDataCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DiagnosticCommandResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    execution, duplicate = await transfer_data(
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
        response.headers["X-Idempotent-Replay"] = "true"
    return command_response(execution, ecu, duplicate=duplicate)


@router.post(
    "/flash/request-transfer-exit",
    response_model=DiagnosticCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_transfer_exit_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: FlashTransferExitCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DiagnosticCommandResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    execution, duplicate = await request_transfer_exit(
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
        response.headers["X-Idempotent-Replay"] = "true"
    return command_response(execution, ecu, duplicate=duplicate)


@router.get("/security-access/state", response_model=SecurityAccessStateResponse)
async def get_security_access_state_endpoint(
    vehicle_id: str,
    ecu_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(diagnostics_read)],
) -> SecurityAccessStateResponse:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    diagnostic_state = await get_or_create_session(session, ecu=ecu)
    security_state = await get_or_create_security_state(session, ecu=ecu)
    await session.commit()
    return security_state_response(security_state, diagnostic_state, ecu)


@router.post(
    "/security-access",
    response_model=DiagnosticCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def security_access_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: SecurityAccessCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DiagnosticCommandResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    try:
        execution, duplicate = await security_access(
            session,
            vehicle=vehicle,
            ecu=ecu,
            command=command,
            actor_user_id=actor.id,
            correlation_id=request_correlation_id(request),
        )
    except DiagnosticContractError:
        # Invalid-key attempts are versioned evidence and must survive the negative response.
        await session.commit()
        raise
    await session.commit()
    await session.refresh(execution, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
        response.headers["X-Idempotent-Replay"] = "true"
    return command_response(execution, ecu, duplicate=duplicate)


@router.post("/routines", response_model=RoutineResponse, status_code=status.HTTP_201_CREATED)
async def create_routine_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: RoutineCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> RoutineResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    routine, routine_state = await create_routine(
        session,
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(routine, attribute_names=["created_at"])
    await session.refresh(routine_state, attribute_names=["updated_at"])
    return routine_response(routine, routine_state, ecu)


@router.get("/routines", response_model=RoutinePage)
async def list_routines_endpoint(
    vehicle_id: str,
    ecu_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(diagnostics_read)],
    limit: Annotated[int, Query(ge=1, le=64)] = 64,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> RoutinePage:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    items, total = await list_routines(session, ecu=ecu, limit=limit, offset=offset)
    return RoutinePage(
        items=[routine_response(routine, state, ecu) for routine, state in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/routines/{identifier}/control",
    response_model=DiagnosticCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def control_routine_endpoint(
    vehicle_id: str,
    ecu_id: str,
    identifier: Annotated[int, Path(ge=0, le=0xFFFF)],
    command: RoutineControlCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DiagnosticCommandResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    execution, duplicate = await control_routine(
        session,
        vehicle=vehicle,
        ecu=ecu,
        identifier=identifier,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(execution, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
        response.headers["X-Idempotent-Replay"] = "true"
    return command_response(execution, ecu, duplicate=duplicate)


@router.get("/routines/{identifier}", response_model=RoutineResponse)
async def get_routine_endpoint(
    vehicle_id: str,
    ecu_id: str,
    identifier: Annotated[int, Path(ge=0, le=0xFFFF)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(diagnostics_read)],
) -> RoutineResponse:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    routine, routine_state = await require_routine(session, ecu=ecu, identifier=identifier)
    return routine_response(routine, routine_state, ecu)


@router.post("/dids", response_model=DidResponse, status_code=status.HTTP_201_CREATED)
async def create_did_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: DidCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DidResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    did = await create_did(
        session,
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(did, attribute_names=["created_at", "updated_at"])
    return did_response(did, ecu)


@router.get("/dids", response_model=DidPage)
async def list_dids_endpoint(
    vehicle_id: str,
    ecu_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(diagnostics_read)],
    limit: Annotated[int, Query(ge=1, le=128)] = 100,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> DidPage:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    items, total = await list_dids(session, ecu=ecu, limit=limit, offset=offset)
    return DidPage(
        items=[did_response(item, ecu) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/dids/read",
    response_model=DiagnosticCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def read_dids_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: DidReadCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_read)],
) -> DiagnosticCommandResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    execution, duplicate = await read_dids(
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
        response.headers["X-Idempotent-Replay"] = "true"
    return command_response(execution, ecu, duplicate=duplicate)


@router.post(
    "/dids/{identifier}/write",
    response_model=DiagnosticCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def write_did_endpoint(
    vehicle_id: str,
    ecu_id: str,
    identifier: Annotated[int, Path(ge=0, le=0xFFFF)],
    command: DidWriteCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DiagnosticCommandResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    execution, duplicate = await write_did(
        session,
        vehicle=vehicle,
        ecu=ecu,
        identifier=identifier,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(execution, attribute_names=["created_at"])
    if duplicate:
        response.status_code = status.HTTP_200_OK
        response.headers["X-Idempotent-Replay"] = "true"
    return command_response(execution, ecu, duplicate=duplicate)


@router.get("/dids/{identifier}", response_model=DidResponse)
async def get_did_endpoint(
    vehicle_id: str,
    ecu_id: str,
    identifier: Annotated[int, Path(ge=0, le=0xFFFF)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(diagnostics_read)],
) -> DidResponse:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    return did_response(await require_did(session, ecu=ecu, identifier=identifier), ecu)


@router.get("/session", response_model=DiagnosticSessionResponse)
async def get_session_endpoint(
    vehicle_id: str,
    ecu_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(diagnostics_read)],
) -> DiagnosticSessionResponse:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    state = await get_or_create_session(session, ecu=ecu)
    await session.commit()
    return DiagnosticSessionResponse(
        ecu_id=ecu.identifier,
        session_type=state.session_type,
        security_level=state.security_level,
        version=state.version,
        simulation_time_ms=state.simulation_time_ms,
    )


@router.post(
    "/session-control",
    response_model=DiagnosticCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def control_session_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: DiagnosticSessionControlCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DiagnosticCommandResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    execution, duplicate = await control_session(
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
    return command_response(execution, ecu, duplicate=duplicate)


@router.post(
    "/ecu-reset",
    response_model=DiagnosticCommandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reset_ecu_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: DiagnosticEcuResetCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DiagnosticCommandResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    execution, duplicate = await reset_ecu(
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
        response.headers["X-Idempotent-Replay"] = "true"
    return command_response(execution, ecu, duplicate=duplicate)


@router.post("/dtcs", response_model=DtcResponse, status_code=status.HTTP_201_CREATED)
async def report_dtc_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: DtcReportCommand,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DtcResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    dtc = await report_dtc(
        session,
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(dtc, attribute_names=["created_at", "updated_at"])
    return dtc_response(dtc, ecu)


@router.get("/dtcs", response_model=DtcPage)
async def list_dtcs_endpoint(
    vehicle_id: str,
    ecu_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(diagnostics_read)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_mask: Annotated[int | None, Query(ge=1, le=255)] = None,
) -> DtcPage:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    items, total = await list_dtcs(
        session, ecu=ecu, limit=limit, offset=offset, status_mask=status_mask
    )
    return DtcPage(
        items=[dtc_response(item, ecu) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/dtcs/{code}", response_model=DtcResponse)
async def get_dtc_endpoint(
    vehicle_id: str,
    ecu_id: str,
    code: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(diagnostics_read)],
) -> DtcResponse:
    _vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    return dtc_response(await require_dtc(session, ecu=ecu, code=code.upper()), ecu)


@router.post("/dtcs/clear", response_model=DiagnosticCommandResponse)
async def clear_dtcs_endpoint(
    vehicle_id: str,
    ecu_id: str,
    command: DtcClearCommand,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(diagnostics_manage)],
) -> DiagnosticCommandResponse:
    vehicle, ecu = await _context(session, vehicle_id=vehicle_id, ecu_id=ecu_id)
    execution, duplicate = await clear_dtcs(
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
        response.headers["X-Idempotent-Replay"] = "true"
    return command_response(execution, ecu, duplicate=duplicate)
