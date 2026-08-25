from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    DiagnosticCommandConflictError,
    DiagnosticContractError,
    ResourceNotFoundError,
)
from atep.diagnostics.models import (
    DiagnosticCommand,
    DiagnosticSessionState,
    DiagnosticTroubleCode,
)
from atep.diagnostics.schemas import (
    DiagnosticSessionControlCommand,
    DtcClearCommand,
    DtcReportCommand,
    UdsNegativeResponseCode,
    UdsServiceId,
)
from atep.ecus.models import ElectronicControlUnit
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


async def get_or_create_session(
    session: AsyncSession, *, ecu: ElectronicControlUnit, lock: bool = False
) -> DiagnosticSessionState:
    query = select(DiagnosticSessionState).where(DiagnosticSessionState.ecu_id == ecu.id)
    if lock:
        query = query.with_for_update()
    state = await session.scalar(query)
    if state is None:
        state = DiagnosticSessionState(
            ecu_id=ecu.id,
            session_type="default",
            security_level=0,
            version=1,
            simulation_time_ms=ecu.simulation_time_ms,
        )
        session.add(state)
        await session.flush()
    return state


async def control_session(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: DiagnosticSessionControlCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[DiagnosticCommand, bool]:
    request = command.model_dump(mode="json")
    existing = await _existing_command(session, ecu=ecu, command_id=command.command_id)
    if existing is not None:
        if (
            existing.service_id == UdsServiceId.DIAGNOSTIC_SESSION_CONTROL
            and existing.request == request
        ):
            return existing, True
        raise DiagnosticCommandConflictError()
    state = await get_or_create_session(session, ecu=ecu, lock=True)
    if command.expected_version != state.version:
        raise DiagnosticContractError(
            reason=f"session version is {state.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    previous_version = state.version
    state.session_type = command.session_type.value
    state.security_level = 0
    state.simulation_time_ms = ecu.simulation_time_ms
    state.version += 1
    result = {
        "session_type": state.session_type,
        "security_level": state.security_level,
        "simulation_time_ms": state.simulation_time_ms,
    }
    execution = DiagnosticCommand(
        ecu_id=ecu.id,
        command_id=command.command_id,
        service_id=UdsServiceId.DIAGNOSTIC_SESSION_CONTROL,
        request=request,
        result=result,
        previous_version=previous_version,
        session_version=state.version,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    _record_evidence(
        session,
        vehicle=vehicle,
        ecu=ecu,
        execution=execution,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        event_type="atep.diagnostics.session.changed.v1",
        action="diagnostics.session_changed",
    )
    return execution, False


async def report_dtc(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: DtcReportCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> DiagnosticTroubleCode:
    dtc = await session.scalar(
        select(DiagnosticTroubleCode)
        .where(DiagnosticTroubleCode.ecu_id == ecu.id, DiagnosticTroubleCode.code == command.code)
        .with_for_update()
    )
    if dtc is None:
        total = await session.scalar(
            select(func.count()).where(DiagnosticTroubleCode.ecu_id == ecu.id)
        )
        if int(total or 0) >= 200:
            raise DiagnosticContractError(
                reason="an ECU may store at most 200 DTCs in V-1",
                negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
            )
        dtc = DiagnosticTroubleCode(
            ecu_id=ecu.id,
            code=command.code,
            status_mask=command.status_mask,
            severity=command.severity.value,
            description=command.description,
            occurrence_count=1,
            first_seen_ms=ecu.simulation_time_ms,
            last_seen_ms=ecu.simulation_time_ms,
            snapshot=command.snapshot,
            version=1,
        )
        session.add(dtc)
    else:
        dtc.status_mask = command.status_mask
        dtc.severity = command.severity.value
        dtc.description = command.description
        dtc.occurrence_count += 1
        dtc.last_seen_ms = ecu.simulation_time_ms
        dtc.snapshot = command.snapshot
        dtc.version += 1
    await session.flush()
    evidence = {
        **_base_evidence(vehicle, ecu),
        "dtc_id": str(dtc.id),
        "code": dtc.code,
        "status_mask": dtc.status_mask,
        "severity": dtc.severity,
        "occurrence_count": dtc.occurrence_count,
        "version": dtc.version,
        "simulation_time_ms": dtc.last_seen_ms,
    }
    enqueue_event(
        session,
        event_type="atep.diagnostics.dtc.reported.v1",
        aggregate_type="diagnostic_trouble_code",
        aggregate_id=dtc.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="diagnostics.dtc_reported",
        resource_type="diagnostic_trouble_code",
        resource_id=dtc.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return dtc


async def list_dtcs(
    session: AsyncSession,
    *,
    ecu: ElectronicControlUnit,
    limit: int,
    offset: int,
    status_mask: int | None,
) -> tuple[list[DiagnosticTroubleCode], int]:
    query = select(DiagnosticTroubleCode).where(DiagnosticTroubleCode.ecu_id == ecu.id)
    if status_mask is not None:
        query = query.where(DiagnosticTroubleCode.status_mask.op("&")(status_mask) != 0)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(DiagnosticTroubleCode.code).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def require_dtc(
    session: AsyncSession, *, ecu: ElectronicControlUnit, code: str
) -> DiagnosticTroubleCode:
    dtc = await session.scalar(
        select(DiagnosticTroubleCode).where(
            DiagnosticTroubleCode.ecu_id == ecu.id, DiagnosticTroubleCode.code == code
        )
    )
    if dtc is None:
        raise ResourceNotFoundError("diagnostic trouble code")
    return dtc


async def clear_dtcs(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: DtcClearCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[DiagnosticCommand, bool]:
    request = command.model_dump(mode="json")
    existing = await _existing_command(session, ecu=ecu, command_id=command.command_id)
    if existing is not None:
        if (
            existing.service_id == UdsServiceId.CLEAR_DIAGNOSTIC_INFORMATION
            and existing.request == request
        ):
            return existing, True
        raise DiagnosticCommandConflictError()
    state = await get_or_create_session(session, ecu=ecu, lock=True)
    if command.expected_version != state.version:
        raise DiagnosticContractError(
            reason=f"session version is {state.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if command.group != "FFFFFF":
        raise DiagnosticContractError(
            reason="only the all-DTC group FFFFFF is supported in V-1",
            negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
        )
    dtcs, _ = await list_dtcs(session, ecu=ecu, limit=200, offset=0, status_mask=None)
    for dtc in dtcs:
        await session.delete(dtc)
    previous_version = state.version
    state.version += 1
    state.simulation_time_ms = ecu.simulation_time_ms
    result = {"group": command.group, "cleared_count": len(dtcs)}
    execution = DiagnosticCommand(
        ecu_id=ecu.id,
        command_id=command.command_id,
        service_id=UdsServiceId.CLEAR_DIAGNOSTIC_INFORMATION,
        request=request,
        result=result,
        previous_version=previous_version,
        session_version=state.version,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    _record_evidence(
        session,
        vehicle=vehicle,
        ecu=ecu,
        execution=execution,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        event_type="atep.diagnostics.dtc.cleared.v1",
        action="diagnostics.dtc_cleared",
    )
    return execution, False


async def _existing_command(
    session: AsyncSession, *, ecu: ElectronicControlUnit, command_id: str
) -> DiagnosticCommand | None:
    existing: DiagnosticCommand | None = await session.scalar(
        select(DiagnosticCommand).where(
            DiagnosticCommand.ecu_id == ecu.id, DiagnosticCommand.command_id == command_id
        )
    )
    return existing


def _record_evidence(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    execution: DiagnosticCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    event_type: str,
    action: str,
) -> None:
    evidence = {
        **_base_evidence(vehicle, ecu),
        "command_id": execution.command_id,
        "service_id": execution.service_id,
        "positive_response_service_id": execution.service_id + 0x40,
        "previous_version": execution.previous_version,
        "session_version": execution.session_version,
        **execution.result,
    }
    enqueue_event(
        session,
        event_type=event_type,
        aggregate_type="ecu",
        aggregate_id=ecu.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action=action,
        resource_type="ecu",
        resource_id=ecu.id,
        correlation_id=correlation_id,
        details=evidence,
    )


def _base_evidence(vehicle: Vehicle, ecu: ElectronicControlUnit) -> dict[str, object]:
    return {
        "vehicle_id": vehicle.identifier,
        "ecu_id": str(ecu.id),
        "ecu_identifier": ecu.identifier,
    }
