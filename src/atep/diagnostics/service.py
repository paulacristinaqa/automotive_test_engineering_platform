import hashlib
import secrets
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    DiagnosticCommandConflictError,
    DiagnosticContractError,
    EcuSimulationCommandConflictError,
    EcuStateVersionConflictError,
    ResourceNotFoundError,
)
from atep.diagnostics.models import (
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
    DiagnosticEcuResetCommand,
    DiagnosticSessionControlCommand,
    DidCreate,
    DidDataType,
    DidReadCommand,
    DidValue,
    DidWriteCommand,
    DtcClearCommand,
    DtcReportCommand,
    FlashRequestDownloadCommand,
    FlashTransferDataCommand,
    FlashTransferExitCommand,
    RoutineControlCommand,
    RoutineControlType,
    RoutineCreate,
    SecurityAccessCommand,
    SecurityAccessType,
    UdsEcuResetType,
    UdsNegativeResponseCode,
    UdsServiceId,
)
from atep.ecus.models import ElectronicControlUnit
from atep.ecus.schemas import EcuResetCommand, EcuResetMode
from atep.ecus.service import execute_ecu_reset
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


async def get_or_create_security_state(
    session: AsyncSession, *, ecu: ElectronicControlUnit, lock: bool = False
) -> DiagnosticSecurityState:
    query = select(DiagnosticSecurityState).where(DiagnosticSecurityState.ecu_id == ecu.id)
    if lock:
        query = query.with_for_update()
    state = await session.scalar(query)
    if state is None:
        state = DiagnosticSecurityState(
            ecu_id=ecu.id,
            challenge_counter=0,
            expected_key_digest=None,
            seed_expires_at_ms=None,
            failed_attempts=0,
            locked_until_ms=None,
            target_level=0,
            version=1,
        )
        session.add(state)
        await session.flush()
    return state


async def get_or_create_flash_state(
    session: AsyncSession, *, ecu: ElectronicControlUnit, lock: bool = False
) -> DiagnosticFlashState:
    query = select(DiagnosticFlashState).where(DiagnosticFlashState.ecu_id == ecu.id)
    if lock:
        query = query.with_for_update()
    state = await session.scalar(query)
    if state is None:
        state = DiagnosticFlashState(
            ecu_id=ecu.id,
            status="idle",
            memory_address=0,
            memory_size=0,
            firmware_version="",
            target_ecu_version=ecu.version,
            max_block_length=256,
            next_block_sequence_counter=1,
            bytes_received=0,
            image_data=b"",
            image_sha256=None,
            version=1,
        )
        session.add(state)
        await session.flush()
    return state


def derive_simulated_security_key(seed: str, level: int = 1) -> str:
    """Return the deterministic V-4 simulator key; this is not production cryptography."""
    return hashlib.sha256(f"ATEP-V4:{level}:{seed}".encode()).hexdigest()[:16].upper()


async def security_access(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: SecurityAccessCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[DiagnosticCommand, bool]:
    key_value = command.key.get_secret_value().upper() if command.key is not None else None
    key_digest = hashlib.sha256(key_value.encode()).hexdigest() if key_value is not None else None
    request = {
        "command_id": command.command_id,
        "access_type": int(command.access_type),
        "expected_session_version": command.expected_session_version,
        "expected_security_version": command.expected_security_version,
        **({"key_sha256": key_digest} if key_digest is not None else {}),
    }
    existing = await _existing_command(session, ecu=ecu, command_id=command.command_id)
    if existing is not None:
        if existing.service_id != UdsServiceId.SECURITY_ACCESS or existing.request != request:
            raise DiagnosticCommandConflictError()
        if existing.result.get("accepted") is False:
            raise _security_denial_from_result(existing.result)
        return existing, True

    diagnostic_session = await get_or_create_session(session, ecu=ecu, lock=True)
    security_state = await get_or_create_security_state(session, ecu=ecu, lock=True)
    if command.expected_session_version != diagnostic_session.version:
        raise DiagnosticContractError(
            reason=f"session version is {diagnostic_session.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if command.expected_security_version != security_state.version:
        raise DiagnosticContractError(
            reason=f"security version is {security_state.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if diagnostic_session.session_type == "default":
        raise DiagnosticContractError(
            reason="Security Access is not available in default session",
            negative_response_code=UdsNegativeResponseCode.SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION,
        )
    now_ms = ecu.simulation_time_ms
    if security_state.locked_until_ms is not None and now_ms < security_state.locked_until_ms:
        raise DiagnosticContractError(
            reason=f"security delay is active until logical time {security_state.locked_until_ms}",
            negative_response_code=UdsNegativeResponseCode.REQUIRED_TIME_DELAY_NOT_EXPIRED,
        )
    if security_state.locked_until_ms is not None:
        security_state.locked_until_ms = None
        security_state.failed_attempts = 0

    previous_version = diagnostic_session.version
    if command.access_type == SecurityAccessType.REQUEST_SEED_LEVEL_1:
        security_state.challenge_counter += 1
        seed = (
            hashlib.sha256(
                f"{ecu.id}:{security_state.challenge_counter}:{now_ms}:{security_state.version}".encode()
            )
            .hexdigest()[:16]
            .upper()
        )
        expected_key = derive_simulated_security_key(seed)
        security_state.expected_key_digest = hashlib.sha256(expected_key.encode()).hexdigest()
        security_state.seed_expires_at_ms = now_ms + 30_000
        security_state.target_level = 1
        security_state.version += 1
        result: dict[str, Any] = {
            "accepted": True,
            "access_type": int(command.access_type),
            "seed": seed,
            "seed_expires_at_ms": security_state.seed_expires_at_ms,
            "security_level": diagnostic_session.security_level,
            "security_version": security_state.version,
        }
    else:
        if (
            security_state.expected_key_digest is None
            or security_state.target_level != 1
            or security_state.seed_expires_at_ms is None
            or now_ms > security_state.seed_expires_at_ms
        ):
            raise DiagnosticContractError(
                reason="a valid level-1 seed must be requested before sendKey",
                negative_response_code=UdsNegativeResponseCode.REQUEST_SEQUENCE_ERROR,
            )
        if key_digest is None or not secrets.compare_digest(
            key_digest, security_state.expected_key_digest
        ):
            security_state.failed_attempts += 1
            security_state.version += 1
            locked = security_state.failed_attempts >= 3
            if locked:
                security_state.locked_until_ms = now_ms + 10_000
                security_state.expected_key_digest = None
                security_state.seed_expires_at_ms = None
                security_state.target_level = 0
            negative_code = (
                UdsNegativeResponseCode.EXCEED_NUMBER_OF_ATTEMPTS
                if locked
                else UdsNegativeResponseCode.INVALID_KEY
            )
            result = {
                "accepted": False,
                "access_type": int(command.access_type),
                "failed_attempts": security_state.failed_attempts,
                "locked_until_ms": security_state.locked_until_ms,
                "security_level": diagnostic_session.security_level,
                "security_version": security_state.version,
                "negative_response_code": int(negative_code),
            }
            execution = _new_security_execution(
                ecu=ecu,
                command=command,
                request=request,
                result=result,
                previous_version=previous_version,
                session_version=diagnostic_session.version,
                actor_user_id=actor_user_id,
            )
            session.add(execution)
            await session.flush()
            _record_security_evidence(
                session,
                vehicle=vehicle,
                ecu=ecu,
                execution=execution,
                security_state=security_state,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
            )
            raise _security_denial_from_result(result)
        diagnostic_session.security_level = 1
        diagnostic_session.simulation_time_ms = now_ms
        diagnostic_session.version += 1
        security_state.failed_attempts = 0
        security_state.expected_key_digest = None
        security_state.seed_expires_at_ms = None
        security_state.target_level = 0
        security_state.version += 1
        result = {
            "accepted": True,
            "access_type": int(command.access_type),
            "security_level": diagnostic_session.security_level,
            "security_version": security_state.version,
        }

    execution = _new_security_execution(
        ecu=ecu,
        command=command,
        request=request,
        result=result,
        previous_version=previous_version,
        session_version=diagnostic_session.version,
        actor_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    _record_security_evidence(
        session,
        vehicle=vehicle,
        ecu=ecu,
        execution=execution,
        security_state=security_state,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
    )
    return execution, False


async def create_routine(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: RoutineCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[DiagnosticRoutine, DiagnosticRoutineState]:
    existing = await session.scalar(
        select(DiagnosticRoutine).where(
            DiagnosticRoutine.ecu_id == ecu.id,
            DiagnosticRoutine.identifier == command.identifier,
        )
    )
    if existing is not None:
        raise DiagnosticContractError(
            reason=f"routine 0x{command.identifier:04X} already exists",
            negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
        )
    total = await session.scalar(select(func.count()).where(DiagnosticRoutine.ecu_id == ecu.id))
    if int(total or 0) >= 64:
        raise DiagnosticContractError(
            reason="an ECU may define at most 64 routines in V-3",
            negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
        )
    routine = DiagnosticRoutine(
        ecu_id=ecu.id,
        identifier=command.identifier,
        name=command.name,
        description=command.description,
        allowed_sessions=[item.value for item in command.allowed_sessions],
        execution_time_ms=command.execution_time_ms,
        supports_stop=command.supports_stop,
        result_template=command.result_template,
        version=1,
        created_by_user_id=actor_user_id,
    )
    session.add(routine)
    await session.flush()
    state = DiagnosticRoutineState(
        routine_id=routine.id,
        status="idle",
        invocation_count=0,
        started_at_ms=None,
        completes_at_ms=None,
        stopped_at_ms=None,
        input_parameters={},
        result={},
        version=1,
    )
    session.add(state)
    await session.flush()
    evidence = {
        **_base_evidence(vehicle, ecu),
        "routine_id": str(routine.id),
        "identifier": routine.identifier,
        "identifier_hex": f"0x{routine.identifier:04X}",
        "execution_time_ms": routine.execution_time_ms,
        "supports_stop": routine.supports_stop,
        "definition_version": routine.version,
        "routine_version": state.version,
    }
    enqueue_event(
        session,
        event_type="atep.diagnostics.routine.created.v1",
        aggregate_type="diagnostic_routine",
        aggregate_id=routine.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="diagnostics.routine_created",
        resource_type="diagnostic_routine",
        resource_id=routine.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return routine, state


async def list_routines(
    session: AsyncSession, *, ecu: ElectronicControlUnit, limit: int, offset: int
) -> tuple[list[tuple[DiagnosticRoutine, DiagnosticRoutineState]], int]:
    base = select(DiagnosticRoutine).where(DiagnosticRoutine.ecu_id == ecu.id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    result = await session.execute(
        select(DiagnosticRoutine, DiagnosticRoutineState)
        .join(DiagnosticRoutineState, DiagnosticRoutineState.routine_id == DiagnosticRoutine.id)
        .where(DiagnosticRoutine.ecu_id == ecu.id)
        .order_by(DiagnosticRoutine.identifier)
        .limit(limit)
        .offset(offset)
    )
    return [(routine, state) for routine, state in result.all()], int(total or 0)


async def require_routine(
    session: AsyncSession,
    *,
    ecu: ElectronicControlUnit,
    identifier: int,
    lock: bool = False,
    uds_request: bool = False,
) -> tuple[DiagnosticRoutine, DiagnosticRoutineState]:
    routine_query = select(DiagnosticRoutine).where(
        DiagnosticRoutine.ecu_id == ecu.id,
        DiagnosticRoutine.identifier == identifier,
    )
    if lock:
        routine_query = routine_query.with_for_update()
    routine = await session.scalar(routine_query)
    if routine is None:
        if uds_request:
            raise DiagnosticContractError(
                reason=f"routine 0x{identifier:04X} is not supported",
                negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
            )
        raise ResourceNotFoundError("diagnostic routine")
    state_query = select(DiagnosticRoutineState).where(
        DiagnosticRoutineState.routine_id == routine.id
    )
    if lock:
        state_query = state_query.with_for_update()
    state = await session.scalar(state_query)
    if state is None:
        raise ResourceNotFoundError("diagnostic routine state")
    return routine, state


async def control_routine(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    identifier: int,
    command: RoutineControlCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[DiagnosticCommand, bool]:
    request = {"identifier": identifier, **command.model_dump(mode="json")}
    existing = await _existing_command(session, ecu=ecu, command_id=command.command_id)
    if existing is not None:
        if existing.service_id == UdsServiceId.ROUTINE_CONTROL and existing.request == request:
            return existing, True
        raise DiagnosticCommandConflictError()
    diagnostic_session = await get_or_create_session(session, ecu=ecu, lock=True)
    routine, state = await require_routine(
        session, ecu=ecu, identifier=identifier, lock=True, uds_request=True
    )
    if command.expected_session_version != diagnostic_session.version:
        raise DiagnosticContractError(
            reason=f"session version is {diagnostic_session.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if command.expected_routine_version != state.version:
        raise DiagnosticContractError(
            reason=f"routine version is {state.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if diagnostic_session.session_type not in routine.allowed_sessions:
        raise DiagnosticContractError(
            reason=(
                f"routine 0x{routine.identifier:04X} is not available in "
                f"{diagnostic_session.session_type} session"
            ),
            negative_response_code=UdsNegativeResponseCode.SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION,
        )
    _refresh_routine_state(routine=routine, state=state, simulation_time_ms=ecu.simulation_time_ms)
    if command.control_type == RoutineControlType.START:
        if state.status == "running":
            raise DiagnosticContractError(
                reason="routine is already running",
                negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
            )
        state.status = "running"
        state.invocation_count += 1
        state.started_at_ms = ecu.simulation_time_ms
        state.completes_at_ms = ecu.simulation_time_ms + routine.execution_time_ms
        state.stopped_at_ms = None
        state.input_parameters = command.parameters
        state.result = {}
        state.version += 1
        _refresh_routine_state(
            routine=routine, state=state, simulation_time_ms=ecu.simulation_time_ms
        )
    elif command.control_type == RoutineControlType.STOP:
        if not routine.supports_stop:
            raise DiagnosticContractError(
                reason="routine does not support stopRoutine",
                negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
            )
        if state.status != "running":
            raise DiagnosticContractError(
                reason=f"routine status is {state.status}",
                negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
            )
        state.status = "stopped"
        state.stopped_at_ms = ecu.simulation_time_ms
        state.completes_at_ms = None
        state.result = {}
        state.version += 1
    elif state.status == "idle":
        raise DiagnosticContractError(
            reason="routine has not been started",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    result = {
        "identifier": routine.identifier,
        "identifier_hex": f"0x{routine.identifier:04X}",
        "control_type": int(command.control_type),
        "status": state.status,
        "invocation_count": state.invocation_count,
        "started_at_ms": state.started_at_ms,
        "completes_at_ms": state.completes_at_ms,
        "stopped_at_ms": state.stopped_at_ms,
        "routine_version": state.version,
        "result": state.result,
    }
    execution = DiagnosticCommand(
        ecu_id=ecu.id,
        command_id=command.command_id,
        service_id=UdsServiceId.ROUTINE_CONTROL,
        request=request,
        result=result,
        previous_version=diagnostic_session.version,
        session_version=diagnostic_session.version,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    _record_routine_evidence(
        session,
        vehicle=vehicle,
        ecu=ecu,
        routine=routine,
        state=state,
        execution=execution,
        control_type=command.control_type,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
    )
    return execution, False


async def create_did(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: DidCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> DiagnosticDataIdentifier:
    existing = await session.scalar(
        select(DiagnosticDataIdentifier).where(
            DiagnosticDataIdentifier.ecu_id == ecu.id,
            DiagnosticDataIdentifier.identifier == command.identifier,
        )
    )
    if existing is not None:
        raise DiagnosticContractError(
            reason=f"DID 0x{command.identifier:04X} already exists",
            negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
        )
    total = await session.scalar(
        select(func.count()).where(DiagnosticDataIdentifier.ecu_id == ecu.id)
    )
    if int(total or 0) >= 128:
        raise DiagnosticContractError(
            reason="an ECU may define at most 128 DIDs in V-2",
            negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
        )
    _validate_did_value(command.data_type, command.value, command)
    did = DiagnosticDataIdentifier(
        ecu_id=ecu.id,
        identifier=command.identifier,
        name=command.name,
        description=command.description,
        data_type=command.data_type.value,
        unit=command.unit,
        writable=command.writable,
        readable_sessions=[item.value for item in command.readable_sessions],
        writable_sessions=[item.value for item in command.writable_sessions],
        value=command.value,
        minimum=command.minimum,
        maximum=command.maximum,
        max_length=command.max_length,
        version=1,
        created_by_user_id=actor_user_id,
    )
    session.add(did)
    await session.flush()
    evidence = {
        **_base_evidence(vehicle, ecu),
        "did_id": str(did.id),
        "identifier": did.identifier,
        "identifier_hex": f"0x{did.identifier:04X}",
        "data_type": did.data_type,
        "writable": did.writable,
        "version": did.version,
    }
    _record_did_catalogue_evidence(
        session,
        did=did,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        evidence=evidence,
    )
    return did


async def list_dids(
    session: AsyncSession, *, ecu: ElectronicControlUnit, limit: int, offset: int
) -> tuple[list[DiagnosticDataIdentifier], int]:
    query = select(DiagnosticDataIdentifier).where(DiagnosticDataIdentifier.ecu_id == ecu.id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(DiagnosticDataIdentifier.identifier).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def require_did(
    session: AsyncSession,
    *,
    ecu: ElectronicControlUnit,
    identifier: int,
    lock: bool = False,
    uds_request: bool = False,
) -> DiagnosticDataIdentifier:
    query = select(DiagnosticDataIdentifier).where(
        DiagnosticDataIdentifier.ecu_id == ecu.id,
        DiagnosticDataIdentifier.identifier == identifier,
    )
    if lock:
        query = query.with_for_update()
    did = await session.scalar(query)
    if did is None:
        if uds_request:
            raise DiagnosticContractError(
                reason=f"DID 0x{identifier:04X} is not supported",
                negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
            )
        raise ResourceNotFoundError("diagnostic data identifier")
    return did


async def read_dids(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: DidReadCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[DiagnosticCommand, bool]:
    request = command.model_dump(mode="json")
    existing = await _existing_command(session, ecu=ecu, command_id=command.command_id)
    if existing is not None:
        if (
            existing.service_id == UdsServiceId.READ_DATA_BY_IDENTIFIER
            and existing.request == request
        ):
            return existing, True
        raise DiagnosticCommandConflictError()
    state = await get_or_create_session(session, ecu=ecu, lock=True)
    dids = [
        await require_did(session, ecu=ecu, identifier=item, uds_request=True)
        for item in command.identifiers
    ]
    for did in dids:
        if state.session_type not in did.readable_sessions:
            raise DiagnosticContractError(
                reason=(
                    f"DID 0x{did.identifier:04X} is not readable in {state.session_type} session"
                ),
                negative_response_code=UdsNegativeResponseCode.SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION,
            )
    result = {
        "session_type": state.session_type,
        "items": [
            {
                "identifier": did.identifier,
                "identifier_hex": f"0x{did.identifier:04X}",
                "data_type": did.data_type,
                "unit": did.unit,
                "value": did.value,
                "did_version": did.version,
            }
            for did in dids
        ],
    }
    execution = DiagnosticCommand(
        ecu_id=ecu.id,
        command_id=command.command_id,
        service_id=UdsServiceId.READ_DATA_BY_IDENTIFIER,
        request=request,
        result=result,
        previous_version=state.version,
        session_version=state.version,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    _record_did_command_evidence(
        session,
        vehicle=vehicle,
        ecu=ecu,
        execution=execution,
        dids=dids,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        event_type="atep.diagnostics.did.read.v1",
        action="diagnostics.did_read",
    )
    return execution, False


async def write_did(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    identifier: int,
    command: DidWriteCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[DiagnosticCommand, bool]:
    request = {"identifier": identifier, **command.model_dump(mode="json")}
    existing = await _existing_command(session, ecu=ecu, command_id=command.command_id)
    if existing is not None:
        if (
            existing.service_id == UdsServiceId.WRITE_DATA_BY_IDENTIFIER
            and existing.request == request
        ):
            return existing, True
        raise DiagnosticCommandConflictError()
    state = await get_or_create_session(session, ecu=ecu, lock=True)
    did = await require_did(session, ecu=ecu, identifier=identifier, lock=True, uds_request=True)
    if command.expected_session_version != state.version:
        raise DiagnosticContractError(
            reason=f"session version is {state.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if command.expected_did_version != did.version:
        raise DiagnosticContractError(
            reason=f"DID version is {did.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if not did.writable or state.session_type not in did.writable_sessions:
        raise DiagnosticContractError(
            reason=f"DID 0x{did.identifier:04X} is not writable in {state.session_type} session",
            negative_response_code=UdsNegativeResponseCode.SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION,
        )
    _validate_did_value(DidDataType(did.data_type), command.value, did)
    previous_did_version = did.version
    did.value = command.value
    did.version += 1
    result = {
        "identifier": did.identifier,
        "identifier_hex": f"0x{did.identifier:04X}",
        "value": did.value,
        "previous_did_version": previous_did_version,
        "did_version": did.version,
        "session_type": state.session_type,
    }
    execution = DiagnosticCommand(
        ecu_id=ecu.id,
        command_id=command.command_id,
        service_id=UdsServiceId.WRITE_DATA_BY_IDENTIFIER,
        request=request,
        result=result,
        previous_version=state.version,
        session_version=state.version,
        requested_by_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    _record_did_command_evidence(
        session,
        vehicle=vehicle,
        ecu=ecu,
        execution=execution,
        dids=[did],
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        event_type="atep.diagnostics.did.written.v1",
        action="diagnostics.did_written",
    )
    return execution, False


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
    security_state = await get_or_create_security_state(session, ecu=ecu, lock=True)
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
    security_state.expected_key_digest = None
    security_state.seed_expires_at_ms = None
    security_state.failed_attempts = 0
    security_state.locked_until_ms = None
    security_state.target_level = 0
    security_state.version += 1
    result = {
        "session_type": state.session_type,
        "security_level": state.security_level,
        "simulation_time_ms": state.simulation_time_ms,
        "security_version": security_state.version,
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


async def reset_ecu(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: DiagnosticEcuResetCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[DiagnosticCommand, bool]:
    request = command.model_dump(mode="json")
    existing = await _existing_command(session, ecu=ecu, command_id=command.command_id)
    if existing is not None:
        if existing.service_id == UdsServiceId.ECU_RESET and existing.request == request:
            return existing, True
        raise DiagnosticCommandConflictError()

    diagnostic_session = await get_or_create_session(session, ecu=ecu, lock=True)
    security_state = await get_or_create_security_state(session, ecu=ecu, lock=True)
    if command.expected_session_version != diagnostic_session.version:
        raise DiagnosticContractError(
            reason=f"session version is {diagnostic_session.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if command.expected_security_version != security_state.version:
        raise DiagnosticContractError(
            reason=f"security version is {security_state.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if diagnostic_session.session_type == "default":
        raise DiagnosticContractError(
            reason="ECU Reset is not available in default session",
            negative_response_code=UdsNegativeResponseCode.SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION,
        )
    if (
        command.reset_type in {UdsEcuResetType.HARD_RESET, UdsEcuResetType.KEY_OFF_ON_RESET}
        and diagnostic_session.security_level < 1
    ):
        raise DiagnosticContractError(
            reason="hard and key-off/on resets require security level 1",
            negative_response_code=UdsNegativeResponseCode.SECURITY_ACCESS_DENIED,
        )

    mode = {
        UdsEcuResetType.HARD_RESET: EcuResetMode.HARD,
        UdsEcuResetType.KEY_OFF_ON_RESET: EcuResetMode.POWER_CYCLE,
        UdsEcuResetType.SOFT_RESET: EcuResetMode.SOFT,
    }[command.reset_type]
    try:
        ecu_execution, _ = await execute_ecu_reset(
            session,
            vehicle=vehicle,
            ecu=ecu,
            command=EcuResetCommand(
                command_id=command.command_id,
                expected_version=command.expected_ecu_version,
                mode=mode,
            ),
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
    except EcuStateVersionConflictError as exc:
        raise DiagnosticContractError(
            reason="ECU version does not match the reset request",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        ) from exc
    except EcuSimulationCommandConflictError as exc:
        raise DiagnosticCommandConflictError() from exc
    previous_session_version = diagnostic_session.version
    diagnostic_session.session_type = "default"
    diagnostic_session.security_level = 0
    diagnostic_session.simulation_time_ms = ecu_execution.simulation_time_ms
    diagnostic_session.version += 1
    security_state.expected_key_digest = None
    security_state.seed_expires_at_ms = None
    security_state.failed_attempts = 0
    security_state.locked_until_ms = None
    security_state.target_level = 0
    security_state.version += 1
    result = {
        "reset_type": int(command.reset_type),
        "mode": mode.value,
        "reset_duration_ms": ecu_execution.result["reset_duration_ms"],
        "boot_count": ecu_execution.result["boot_count"],
        "ecu_version": ecu_execution.state_version,
        "simulation_time_ms": ecu_execution.simulation_time_ms,
        "session_type": diagnostic_session.session_type,
        "security_level": diagnostic_session.security_level,
        "security_version": security_state.version,
    }
    execution = DiagnosticCommand(
        ecu_id=ecu.id,
        command_id=command.command_id,
        service_id=UdsServiceId.ECU_RESET,
        request=request,
        result=result,
        previous_version=previous_session_version,
        session_version=diagnostic_session.version,
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
        event_type="atep.diagnostics.ecu.reset.v1",
        action="diagnostics.ecu_reset",
    )
    return execution, False


async def request_download(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: FlashRequestDownloadCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[DiagnosticCommand, bool]:
    request = command.model_dump(mode="json")
    existing = await _existing_command(session, ecu=ecu, command_id=command.command_id)
    if existing is not None:
        if existing.service_id == UdsServiceId.REQUEST_DOWNLOAD and existing.request == request:
            return existing, True
        raise DiagnosticCommandConflictError()

    diagnostic_state = await get_or_create_session(session, ecu=ecu, lock=True)
    security_state = await get_or_create_security_state(session, ecu=ecu, lock=True)
    transfer = await get_or_create_flash_state(session, ecu=ecu, lock=True)
    locked_ecu = await _locked_ecu(session, ecu)
    _require_flash_access(
        diagnostic_state=diagnostic_state,
        security_state=security_state,
        expected_session_version=command.expected_session_version,
        expected_security_version=command.expected_security_version,
    )
    if command.expected_ecu_version != locked_ecu.version:
        raise DiagnosticContractError(
            reason=f"ECU version is {locked_ecu.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if transfer.status == "downloading":
        raise DiagnosticContractError(
            reason="a firmware download is already active",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )

    transfer.status = "downloading"
    transfer.memory_address = command.memory_address
    transfer.memory_size = command.memory_size
    transfer.firmware_version = command.firmware_version
    transfer.target_ecu_version = locked_ecu.version
    transfer.max_block_length = 256
    transfer.next_block_sequence_counter = 1
    transfer.bytes_received = 0
    transfer.image_data = b""
    transfer.image_sha256 = None
    transfer.version += 1
    result = {
        "accepted": True,
        "memory_address": transfer.memory_address,
        "memory_size": transfer.memory_size,
        "firmware_version": transfer.firmware_version,
        "max_block_length": transfer.max_block_length,
        "transfer_version": transfer.version,
    }
    execution = _new_flash_execution(
        ecu=locked_ecu,
        command_id=command.command_id,
        service_id=UdsServiceId.REQUEST_DOWNLOAD,
        request=request,
        result=result,
        session_version=diagnostic_state.version,
        actor_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    _record_evidence(
        session,
        vehicle=vehicle,
        ecu=locked_ecu,
        execution=execution,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        event_type="atep.diagnostics.flash.download.requested.v1",
        action="diagnostics.flash_download_requested",
    )
    return execution, False


async def transfer_data(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: FlashTransferDataCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[DiagnosticCommand, bool]:
    block = bytes.fromhex(command.data_hex.get_secret_value())
    block_sha256 = hashlib.sha256(block).hexdigest()
    request = {
        "command_id": command.command_id,
        "block_sequence_counter": command.block_sequence_counter,
        "block_size": len(block),
        "block_sha256": block_sha256,
        "expected_transfer_version": command.expected_transfer_version,
    }
    existing = await _existing_command(session, ecu=ecu, command_id=command.command_id)
    if existing is not None:
        if existing.service_id == UdsServiceId.TRANSFER_DATA and existing.request == request:
            return existing, True
        raise DiagnosticCommandConflictError()

    diagnostic_state = await get_or_create_session(session, ecu=ecu, lock=True)
    security_state = await get_or_create_security_state(session, ecu=ecu, lock=True)
    transfer = await get_or_create_flash_state(session, ecu=ecu, lock=True)
    _require_active_flash_access(diagnostic_state, security_state)
    if transfer.status != "downloading":
        raise DiagnosticContractError(
            reason="Request Download must start a transfer before Transfer Data",
            negative_response_code=UdsNegativeResponseCode.REQUEST_SEQUENCE_ERROR,
        )
    if command.expected_transfer_version != transfer.version:
        raise DiagnosticContractError(
            reason=f"transfer version is {transfer.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if command.block_sequence_counter != transfer.next_block_sequence_counter:
        raise DiagnosticContractError(
            reason=f"expected block sequence counter {transfer.next_block_sequence_counter}",
            negative_response_code=UdsNegativeResponseCode.WRONG_BLOCK_SEQUENCE_COUNTER,
        )
    if (
        len(block) > transfer.max_block_length
        or transfer.bytes_received + len(block) > transfer.memory_size
    ):
        raise DiagnosticContractError(
            reason="firmware block exceeds the negotiated transfer bounds",
            negative_response_code=(
                UdsNegativeResponseCode.INCORRECT_MESSAGE_LENGTH_OR_INVALID_FORMAT
            ),
        )

    transfer.image_data = bytes(transfer.image_data) + block
    transfer.bytes_received += len(block)
    transfer.next_block_sequence_counter = (
        0
        if transfer.next_block_sequence_counter == 255
        else transfer.next_block_sequence_counter + 1
    )
    transfer.version += 1
    result = {
        "block_sequence_counter": command.block_sequence_counter,
        "block_size": len(block),
        "block_sha256": block_sha256,
        "bytes_received": transfer.bytes_received,
        "remaining_bytes": transfer.memory_size - transfer.bytes_received,
        "next_block_sequence_counter": transfer.next_block_sequence_counter,
        "transfer_version": transfer.version,
    }
    execution = _new_flash_execution(
        ecu=ecu,
        command_id=command.command_id,
        service_id=UdsServiceId.TRANSFER_DATA,
        request=request,
        result=result,
        session_version=diagnostic_state.version,
        actor_user_id=actor_user_id,
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
        event_type="atep.diagnostics.flash.block.transferred.v1",
        action="diagnostics.flash_block_transferred",
    )
    return execution, False


async def request_transfer_exit(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    command: FlashTransferExitCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[DiagnosticCommand, bool]:
    request = command.model_dump(mode="json")
    existing = await _existing_command(session, ecu=ecu, command_id=command.command_id)
    if existing is not None:
        if (
            existing.service_id == UdsServiceId.REQUEST_TRANSFER_EXIT
            and existing.request == request
        ):
            return existing, True
        raise DiagnosticCommandConflictError()

    diagnostic_state = await get_or_create_session(session, ecu=ecu, lock=True)
    security_state = await get_or_create_security_state(session, ecu=ecu, lock=True)
    transfer = await get_or_create_flash_state(session, ecu=ecu, lock=True)
    locked_ecu = await _locked_ecu(session, ecu)
    _require_active_flash_access(diagnostic_state, security_state)
    if transfer.status != "downloading":
        raise DiagnosticContractError(
            reason="no firmware transfer is active",
            negative_response_code=UdsNegativeResponseCode.REQUEST_SEQUENCE_ERROR,
        )
    if command.expected_transfer_version != transfer.version:
        raise DiagnosticContractError(
            reason=f"transfer version is {transfer.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if (
        command.expected_ecu_version != locked_ecu.version
        or locked_ecu.version != transfer.target_ecu_version
    ):
        raise DiagnosticContractError(
            reason=f"ECU version is {locked_ecu.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if transfer.bytes_received != transfer.memory_size:
        raise DiagnosticContractError(
            reason=f"received {transfer.bytes_received} of {transfer.memory_size} bytes",
            negative_response_code=UdsNegativeResponseCode.REQUEST_SEQUENCE_ERROR,
        )
    actual_sha256 = hashlib.sha256(bytes(transfer.image_data)).hexdigest()
    if not secrets.compare_digest(actual_sha256, command.expected_sha256):
        raise DiagnosticContractError(
            reason="firmware image digest does not match",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )

    previous_ecu_version = locked_ecu.version
    locked_ecu.profile_version = transfer.firmware_version
    locked_ecu.version += 1
    transfer.status = "completed"
    transfer.image_sha256 = actual_sha256
    transfer.image_data = b""
    transfer.version += 1
    result = {
        "accepted": True,
        "firmware_version": transfer.firmware_version,
        "image_size": transfer.memory_size,
        "image_sha256": actual_sha256,
        "previous_ecu_version": previous_ecu_version,
        "ecu_version": locked_ecu.version,
        "transfer_version": transfer.version,
    }
    execution = _new_flash_execution(
        ecu=locked_ecu,
        command_id=command.command_id,
        service_id=UdsServiceId.REQUEST_TRANSFER_EXIT,
        request=request,
        result=result,
        session_version=diagnostic_state.version,
        actor_user_id=actor_user_id,
    )
    session.add(execution)
    await session.flush()
    _record_evidence(
        session,
        vehicle=vehicle,
        ecu=locked_ecu,
        execution=execution,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        event_type="atep.diagnostics.flash.completed.v1",
        action="diagnostics.flash_completed",
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


async def _locked_ecu(session: AsyncSession, ecu: ElectronicControlUnit) -> ElectronicControlUnit:
    locked = await session.scalar(
        select(ElectronicControlUnit).where(ElectronicControlUnit.id == ecu.id).with_for_update()
    )
    if locked is None:
        raise ResourceNotFoundError("electronic control unit")
    return locked


def _require_flash_access(
    *,
    diagnostic_state: DiagnosticSessionState,
    security_state: DiagnosticSecurityState,
    expected_session_version: int,
    expected_security_version: int,
) -> None:
    if expected_session_version != diagnostic_state.version:
        raise DiagnosticContractError(
            reason=f"session version is {diagnostic_state.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    if expected_security_version != security_state.version:
        raise DiagnosticContractError(
            reason=f"security version is {security_state.version}",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )
    _require_active_flash_access(diagnostic_state, security_state)


def _require_active_flash_access(
    diagnostic_state: DiagnosticSessionState, security_state: DiagnosticSecurityState
) -> None:
    if diagnostic_state.session_type != "programming":
        raise DiagnosticContractError(
            reason="firmware transfer requires the programming session",
            negative_response_code=UdsNegativeResponseCode.SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION,
        )
    if diagnostic_state.security_level < 1:
        raise DiagnosticContractError(
            reason="firmware transfer requires security level 1",
            negative_response_code=UdsNegativeResponseCode.SECURITY_ACCESS_DENIED,
        )
    if security_state.target_level not in {0, 1}:
        raise DiagnosticContractError(
            reason="invalid diagnostic security state",
            negative_response_code=UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
        )


def _new_flash_execution(
    *,
    ecu: ElectronicControlUnit,
    command_id: str,
    service_id: UdsServiceId,
    request: dict[str, Any],
    result: dict[str, Any],
    session_version: int,
    actor_user_id: UUID,
) -> DiagnosticCommand:
    return DiagnosticCommand(
        ecu_id=ecu.id,
        command_id=command_id,
        service_id=service_id,
        request=request,
        result=result,
        previous_version=session_version,
        session_version=session_version,
        requested_by_user_id=actor_user_id,
    )


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


def _record_did_catalogue_evidence(
    session: AsyncSession,
    *,
    did: DiagnosticDataIdentifier,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    evidence: dict[str, object],
) -> None:
    enqueue_event(
        session,
        event_type="atep.diagnostics.did.created.v1",
        aggregate_type="diagnostic_data_identifier",
        aggregate_id=did.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="diagnostics.did_created",
        resource_type="diagnostic_data_identifier",
        resource_id=did.id,
        correlation_id=correlation_id,
        details=evidence,
    )


def _record_did_command_evidence(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    execution: DiagnosticCommand,
    dids: list[DiagnosticDataIdentifier],
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
        "session_version": execution.session_version,
        "did_count": len(dids),
        "identifiers": [item.identifier for item in dids],
        "did_versions": {str(item.identifier): item.version for item in dids},
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


def _refresh_routine_state(
    *,
    routine: DiagnosticRoutine,
    state: DiagnosticRoutineState,
    simulation_time_ms: int,
) -> None:
    if (
        state.status == "running"
        and state.completes_at_ms is not None
        and simulation_time_ms >= state.completes_at_ms
    ):
        state.status = "completed"
        state.result = routine.result_template
        state.version += 1


def _record_routine_evidence(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    routine: DiagnosticRoutine,
    state: DiagnosticRoutineState,
    execution: DiagnosticCommand,
    control_type: RoutineControlType,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> None:
    evidence = {
        **_base_evidence(vehicle, ecu),
        "command_id": execution.command_id,
        "service_id": execution.service_id,
        "positive_response_service_id": execution.service_id + 0x40,
        "routine_id": str(routine.id),
        "identifier": routine.identifier,
        "identifier_hex": f"0x{routine.identifier:04X}",
        "control_type": int(control_type),
        "status": state.status,
        "invocation_count": state.invocation_count,
        "routine_version": state.version,
        "session_version": execution.session_version,
        "simulation_time_ms": ecu.simulation_time_ms,
    }
    enqueue_event(
        session,
        event_type="atep.diagnostics.routine.controlled.v1",
        aggregate_type="diagnostic_routine",
        aggregate_id=routine.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="diagnostics.routine_controlled",
        resource_type="diagnostic_routine",
        resource_id=routine.id,
        correlation_id=correlation_id,
        details=evidence,
    )


def _new_security_execution(
    *,
    ecu: ElectronicControlUnit,
    command: SecurityAccessCommand,
    request: dict[str, Any],
    result: dict[str, Any],
    previous_version: int,
    session_version: int,
    actor_user_id: UUID,
) -> DiagnosticCommand:
    return DiagnosticCommand(
        ecu_id=ecu.id,
        command_id=command.command_id,
        service_id=UdsServiceId.SECURITY_ACCESS,
        request=request,
        result=result,
        previous_version=previous_version,
        session_version=session_version,
        requested_by_user_id=actor_user_id,
    )


def _security_denial_from_result(result: dict[str, Any]) -> DiagnosticContractError:
    negative_code = int(result["negative_response_code"])
    reason = (
        "security access attempt limit exceeded"
        if negative_code == UdsNegativeResponseCode.EXCEED_NUMBER_OF_ATTEMPTS
        else "security access key is invalid"
    )
    error = DiagnosticContractError(
        reason=reason,
        negative_response_code=negative_code,
    )
    assert error.details is not None
    error.details.update(
        failed_attempts=int(result["failed_attempts"]),
        locked_until_ms=result.get("locked_until_ms"),
        security_version=int(result["security_version"]),
    )
    return error


def _record_security_evidence(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    ecu: ElectronicControlUnit,
    execution: DiagnosticCommand,
    security_state: DiagnosticSecurityState,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> None:
    evidence = {
        **_base_evidence(vehicle, ecu),
        "command_id": execution.command_id,
        "service_id": execution.service_id,
        "positive_response_service_id": execution.service_id + 0x40,
        "access_type": execution.result["access_type"],
        "accepted": execution.result["accepted"],
        "security_level": execution.result["security_level"],
        "failed_attempts": security_state.failed_attempts,
        "locked_until_ms": security_state.locked_until_ms,
        "security_version": security_state.version,
        "session_version": execution.session_version,
        "simulation_time_ms": ecu.simulation_time_ms,
    }
    enqueue_event(
        session,
        event_type="atep.diagnostics.security.accessed.v1",
        aggregate_type="diagnostic_security_state",
        aggregate_id=security_state.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="diagnostics.security_accessed",
        resource_type="diagnostic_security_state",
        resource_id=security_state.id,
        correlation_id=correlation_id,
        details=evidence,
    )


def _validate_did_value(
    data_type: DidDataType,
    value: DidValue,
    definition: DidCreate | DiagnosticDataIdentifier,
) -> None:
    valid = (
        (data_type == DidDataType.BOOLEAN and isinstance(value, bool))
        or (
            data_type == DidDataType.INTEGER
            and isinstance(value, int)
            and not isinstance(value, bool)
        )
        or (
            data_type == DidDataType.DECIMAL
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        )
        or (data_type == DidDataType.STRING and isinstance(value, str))
    )
    if not valid:
        raise DiagnosticContractError(
            reason=f"value does not match DID data type {data_type.value}",
            negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
        )
    minimum = definition.minimum
    maximum = definition.maximum
    if data_type in {DidDataType.INTEGER, DidDataType.DECIMAL}:
        numeric_value = float(value)
        if minimum is not None and numeric_value < minimum:
            raise DiagnosticContractError(
                reason=f"value is below minimum {minimum}",
                negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
            )
        if maximum is not None and numeric_value > maximum:
            raise DiagnosticContractError(
                reason=f"value exceeds maximum {maximum}",
                negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
            )
    if data_type == DidDataType.STRING and definition.max_length is not None:
        if len(str(value)) > definition.max_length:
            raise DiagnosticContractError(
                reason=f"value exceeds maximum length {definition.max_length}",
                negative_response_code=UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
            )


def _base_evidence(vehicle: Vehicle, ecu: ElectronicControlUnit) -> dict[str, object]:
    return {
        "vehicle_id": vehicle.identifier,
        "ecu_id": str(ecu.id),
        "ecu_identifier": ecu.identifier,
    }
