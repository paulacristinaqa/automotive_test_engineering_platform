from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.diagnostics.models import DiagnosticCommand, DiagnosticTroubleCode
from atep.diagnostics.schemas import (
    DiagnosticCommandResponse,
    DiagnosticSessionControlCommand,
    DiagnosticSessionResponse,
    DtcClearCommand,
    DtcPage,
    DtcReportCommand,
    DtcResponse,
)
from atep.diagnostics.service import (
    clear_dtcs,
    control_session,
    get_or_create_session,
    list_dtcs,
    report_dtc,
    require_dtc,
)
from atep.ecus.models import ElectronicControlUnit
from atep.ecus.service import require_ecu
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.vehicles.models import Vehicle
from atep.vehicles.service import require_vehicle

router = APIRouter(
    prefix="/vehicles/{vehicle_id}/ecus/{ecu_id}/diagnostics", tags=["diagnostics"]
)
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
