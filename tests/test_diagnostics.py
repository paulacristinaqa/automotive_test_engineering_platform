import hashlib
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import DiagnosticCommandConflictError, DiagnosticContractError
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
    DiagnosticSessionType,
    DidCreate,
    DidReadCommand,
    DidWriteCommand,
    DtcReportCommand,
    FlashRequestDownloadCommand,
    FlashTransferDataCommand,
    FlashTransferExitCommand,
    RoutineControlCommand,
    RoutineCreate,
    SecurityAccessCommand,
    UdsEcuResetType,
    UdsNegativeResponseCode,
)
from atep.diagnostics.service import (
    control_routine,
    control_session,
    create_did,
    create_routine,
    derive_simulated_security_key,
    read_dids,
    report_dtc,
    request_download,
    request_transfer_exit,
    reset_ecu,
    security_access,
    transfer_data,
    write_did,
)
from atep.ecus.models import ElectronicControlUnit
from atep.events.models import OutboxEvent
from atep.identity.dependencies import require_permissions
from atep.identity.permissions import PermissionName
from atep.vehicles.models import Vehicle


class FakeSession:
    def __init__(self, *scalar_values: Any) -> None:
        self.scalar_values = list(scalar_values)
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()


def vehicle_and_ecu() -> tuple[Vehicle, ElectronicControlUnit]:
    now = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
    vehicle = Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP Reference Vehicle",
        model="EV",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )
    ecu = ElectronicControlUnit(
        id=uuid4(),
        vehicle_id=vehicle.id,
        identifier="bms-ecu",
        display_name="Battery Management ECU",
        ecu_type="battery",
        operational_state="running",
        memory=[],
        memory_regions=[],
        faults=[],
        signals=[],
        cyclic_tasks=[],
        version=4,
        simulation_time_ms=2_500,
        boot_count=1,
        profile_version="1.0.0",
        behavior_state={},
        created_at=now,
        updated_at=now,
    )
    return vehicle, ecu


def test_diagnostic_contracts_are_bounded_and_hex_normalized() -> None:
    valid = DtcReportCommand(code="0A80FF", status_mask=0x09)
    assert valid.code == "0A80FF"
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        DtcReportCommand(code="P0A80", status_mask=1)
    with pytest.raises(ValidationError, match="less than or equal to 255"):
        DtcReportCommand(code="0A80FF", status_mask=256)
    with pytest.raises(ValidationError, match="at most 32"):
        DtcReportCommand(
            code="0A80FF",
            status_mask=1,
            snapshot={f"signal-{index}": index for index in range(33)},
        )


def writable_temperature_did(ecu: ElectronicControlUnit) -> DiagnosticDataIdentifier:
    return DiagnosticDataIdentifier(
        id=uuid4(),
        ecu_id=ecu.id,
        identifier=0xF190,
        name="Battery temperature",
        description="",
        data_type="decimal",
        unit="celsius",
        writable=True,
        readable_sessions=["default", "extended"],
        writable_sessions=["extended"],
        value=24.5,
        minimum=-40.0,
        maximum=100.0,
        max_length=None,
        version=1,
        created_by_user_id=uuid4(),
    )


def battery_balance_routine(
    ecu: ElectronicControlUnit,
) -> tuple[DiagnosticRoutine, DiagnosticRoutineState]:
    routine = DiagnosticRoutine(
        id=uuid4(),
        ecu_id=ecu.id,
        identifier=0x0201,
        name="Battery cell balancing",
        description="",
        allowed_sessions=["extended"],
        execution_time_ms=500,
        supports_stop=True,
        result_template={"balanced": True, "delta_mv": 4.2},
        version=1,
        created_by_user_id=uuid4(),
    )
    state = DiagnosticRoutineState(
        id=uuid4(),
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
    return routine, state


def security_state(ecu: ElectronicControlUnit, *, version: int = 1) -> DiagnosticSecurityState:
    return DiagnosticSecurityState(
        id=uuid4(),
        ecu_id=ecu.id,
        challenge_counter=0,
        expected_key_digest=None,
        seed_expires_at_ms=None,
        failed_attempts=0,
        locked_until_ms=None,
        target_level=0,
        version=version,
    )


def flash_state(ecu: ElectronicControlUnit, *, version: int = 1) -> DiagnosticFlashState:
    return DiagnosticFlashState(
        id=uuid4(),
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
        version=version,
    )


def test_security_access_contract_masks_and_requires_key_by_subfunction() -> None:
    command = SecurityAccessCommand(
        command_id="security-key-masked",
        access_type=2,
        expected_session_version=1,
        expected_security_version=1,
        key="0011223344556677",
    )
    assert "0011223344556677" not in repr(command)
    with pytest.raises(ValidationError, match="sendKey requires a key"):
        SecurityAccessCommand(
            command_id="security-missing-key",
            access_type=2,
            expected_session_version=1,
            expected_security_version=1,
        )
    with pytest.raises(ValidationError, match="requestSeed must not contain a key"):
        SecurityAccessCommand(
            command_id="security-seed-with-key",
            access_type=1,
            expected_session_version=1,
            expected_security_version=1,
            key="0011223344556677",
        )
    with pytest.raises(ValidationError, match="16 hexadecimal") as error:
        SecurityAccessCommand(
            command_id="security-nonhex-key",
            access_type=2,
            expected_session_version=1,
            expected_security_version=1,
            key="NOT-A-VALID-KEY!",
        )
    assert "NOT-A-VALID-KEY!" not in str(error.value)


@pytest.mark.asyncio
async def test_uds_ecu_reset_is_atomic_idempotent_and_resets_diagnostics() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(),
        ecu_id=ecu.id,
        session_type="extended",
        security_level=1,
        version=5,
        simulation_time_ms=ecu.simulation_time_ms,
    )
    access_state = DiagnosticSecurityState(
        id=uuid4(),
        ecu_id=ecu.id,
        challenge_counter=3,
        expected_key_digest="a" * 64,
        seed_expires_at_ms=30_000,
        failed_attempts=2,
        locked_until_ms=12_000,
        target_level=1,
        version=7,
    )
    command = DiagnosticEcuResetCommand(
        command_id="uds-ecu-reset-001",
        reset_type=1,
        expected_ecu_version=4,
        expected_session_version=5,
        expected_security_version=7,
    )
    session = FakeSession(None, diagnostic_state, access_state, ecu, None)

    execution, duplicate = await reset_ecu(
        cast(AsyncSession, session),
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )

    assert duplicate is False
    assert execution.service_id == 0x11
    assert execution.result["reset_type"] == 0x01
    assert execution.result["mode"] == "hard"
    assert execution.result["reset_duration_ms"] == 100
    assert execution.result["ecu_version"] == 5
    assert execution.result["simulation_time_ms"] == 2_600
    assert ecu.operational_state == "offline"
    assert ecu.boot_count == 2
    assert diagnostic_state.session_type == "default"
    assert diagnostic_state.security_level == 0
    assert diagnostic_state.version == 6
    assert diagnostic_state.simulation_time_ms == 2_600
    assert access_state.expected_key_digest is None
    assert access_state.seed_expires_at_ms is None
    assert access_state.failed_attempts == 0
    assert access_state.locked_until_ms is None
    assert access_state.target_level == 0
    assert access_state.version == 8
    events = [item.event_type for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item.action for item in session.added if isinstance(item, AuditRecord)]
    assert events == ["atep.ecu.reset.completed.v1", "atep.diagnostics.ecu.reset.v1"]
    assert audits == ["ecu.reset_completed", "diagnostics.ecu_reset"]

    replayed, duplicate = await reset_ecu(
        cast(AsyncSession, FakeSession(execution)),
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert replayed is execution
    assert duplicate is True


@pytest.mark.asyncio
async def test_uds_ecu_reset_enforces_session_and_security_policy() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(),
        ecu_id=ecu.id,
        session_type="extended",
        security_level=0,
        version=2,
        simulation_time_ms=ecu.simulation_time_ms,
    )
    access_state = security_state(ecu, version=3)
    hard_reset = DiagnosticEcuResetCommand(
        command_id="uds-hard-reset-denied",
        reset_type=1,
        expected_ecu_version=4,
        expected_session_version=2,
        expected_security_version=3,
    )
    with pytest.raises(DiagnosticContractError) as error:
        await reset_ecu(
            cast(AsyncSession, FakeSession(None, diagnostic_state, access_state)),
            vehicle=vehicle,
            ecu=ecu,
            command=hard_reset,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x33

    diagnostic_state.session_type = "default"
    soft_reset = hard_reset.model_copy(
        update={
            "command_id": "uds-soft-reset-default",
            "reset_type": UdsEcuResetType.SOFT_RESET,
        }
    )
    with pytest.raises(DiagnosticContractError) as error:
        await reset_ecu(
            cast(AsyncSession, FakeSession(None, diagnostic_state, access_state)),
            vehicle=vehicle,
            ecu=ecu,
            command=soft_reset,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x7F


@pytest.mark.asyncio
async def test_uds_flash_pipeline_is_bounded_atomic_and_digest_verified() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(),
        ecu_id=ecu.id,
        session_type="programming",
        security_level=1,
        version=4,
        simulation_time_ms=ecu.simulation_time_ms,
    )
    access_state = security_state(ecu, version=3)
    transfer = flash_state(ecu, version=1)
    image = bytes.fromhex("0102030405060708")
    digest = hashlib.sha256(image).hexdigest()

    download, duplicate = await request_download(
        cast(AsyncSession, FakeSession(None, diagnostic_state, access_state, transfer, ecu)),
        vehicle=vehicle,
        ecu=ecu,
        command=FlashRequestDownloadCommand(
            command_id="flash-download-001",
            memory_address=0x8000,
            memory_size=len(image),
            firmware_version="2.0.0",
            expected_ecu_version=4,
            expected_session_version=4,
            expected_security_version=3,
        ),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert download.service_id == 0x34
    assert transfer.status == "downloading"
    assert transfer.version == 2
    assert transfer.max_block_length == 256

    block_session = FakeSession(None, diagnostic_state, access_state, transfer)
    block, duplicate = await transfer_data(
        cast(AsyncSession, block_session),
        vehicle=vehicle,
        ecu=ecu,
        command=FlashTransferDataCommand(
            command_id="flash-block-001",
            block_sequence_counter=1,
            data_hex=image.hex(),
            expected_transfer_version=2,
        ),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert block.service_id == 0x36
    assert block.request["block_sha256"] == digest
    assert "data_hex" not in block.request
    assert transfer.bytes_received == len(image)
    assert transfer.version == 3

    exit_session = FakeSession(None, diagnostic_state, access_state, transfer, ecu)
    completed, duplicate = await request_transfer_exit(
        cast(AsyncSession, exit_session),
        vehicle=vehicle,
        ecu=ecu,
        command=FlashTransferExitCommand(
            command_id="flash-exit-001",
            expected_transfer_version=3,
            expected_ecu_version=4,
            expected_sha256=digest,
        ),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert completed.service_id == 0x37
    assert completed.result["image_sha256"] == digest
    assert transfer.status == "completed"
    assert transfer.image_data == b""
    assert transfer.version == 4
    assert ecu.profile_version == "2.0.0"
    assert ecu.version == 5
    events = [item.event_type for item in exit_session.added if isinstance(item, OutboxEvent)]
    assert events == ["atep.diagnostics.flash.completed.v1"]


@pytest.mark.asyncio
async def test_uds_flash_rejects_wrong_sequence_and_incomplete_image() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(),
        ecu_id=ecu.id,
        session_type="programming",
        security_level=1,
        version=1,
        simulation_time_ms=ecu.simulation_time_ms,
    )
    access_state = security_state(ecu)
    transfer = flash_state(ecu, version=2)
    transfer.status = "downloading"
    transfer.memory_size = 8
    transfer.firmware_version = "2.0.0"
    transfer.target_ecu_version = ecu.version

    with pytest.raises(DiagnosticContractError) as error:
        await transfer_data(
            cast(AsyncSession, FakeSession(None, diagnostic_state, access_state, transfer)),
            vehicle=vehicle,
            ecu=ecu,
            command=FlashTransferDataCommand(
                command_id="flash-wrong-sequence",
                block_sequence_counter=2,
                data_hex="0102",
                expected_transfer_version=2,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x73

    with pytest.raises(DiagnosticContractError) as error:
        await request_transfer_exit(
            cast(AsyncSession, FakeSession(None, diagnostic_state, access_state, transfer, ecu)),
            vehicle=vehicle,
            ecu=ecu,
            command=FlashTransferExitCommand(
                command_id="flash-incomplete",
                expected_transfer_version=2,
                expected_ecu_version=4,
                expected_sha256=hashlib.sha256(b"").hexdigest(),
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x24


@pytest.mark.asyncio
async def test_uds_flash_block_counter_wraps_from_255_to_zero() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(),
        ecu_id=ecu.id,
        session_type="programming",
        security_level=1,
        version=1,
        simulation_time_ms=ecu.simulation_time_ms,
    )
    access_state = security_state(ecu)
    transfer = flash_state(ecu, version=8)
    transfer.status = "downloading"
    transfer.memory_size = 1
    transfer.next_block_sequence_counter = 255

    await transfer_data(
        cast(AsyncSession, FakeSession(None, diagnostic_state, access_state, transfer)),
        vehicle=vehicle,
        ecu=ecu,
        command=FlashTransferDataCommand(
            command_id="flash-block-wrap",
            block_sequence_counter=255,
            data_hex="01",
            expected_transfer_version=8,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert transfer.next_block_sequence_counter == 0


@pytest.mark.asyncio
async def test_security_seed_is_deterministic_replayable_and_not_shared() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(), ecu_id=ecu.id, session_type="extended", version=3, simulation_time_ms=2_500
    )
    access_state = security_state(ecu)
    command = SecurityAccessCommand(
        command_id="security-seed-001",
        access_type=1,
        expected_session_version=3,
        expected_security_version=1,
    )
    session = FakeSession(None, diagnostic_state, access_state)
    execution, duplicate = await security_access(
        cast(AsyncSession, session),
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is False
    assert execution.service_id == 0x27
    assert execution.result["seed"]
    assert execution.result["seed_expires_at_ms"] == 32_500
    assert access_state.expected_key_digest is not None
    assert access_state.version == 2
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    for forbidden in ("seed", "key", "key_sha256", "expected_key_digest"):
        assert forbidden not in event.payload
        assert forbidden not in audit.details

    returned, duplicate = await security_access(
        cast(AsyncSession, FakeSession(execution)),
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is execution
    assert duplicate is True
    assert access_state.version == 2


@pytest.mark.asyncio
async def test_security_valid_key_unlocks_level_one_without_storing_raw_key() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(), ecu_id=ecu.id, session_type="extended", version=3, simulation_time_ms=2_500
    )
    access_state = security_state(ecu, version=2)
    seed = "0123456789ABCDEF"
    key = derive_simulated_security_key(seed)
    access_state.challenge_counter = 1
    access_state.expected_key_digest = hashlib.sha256(key.encode()).hexdigest()
    access_state.seed_expires_at_ms = 32_500
    access_state.target_level = 1
    command = SecurityAccessCommand(
        command_id="security-key-001",
        access_type=2,
        expected_session_version=3,
        expected_security_version=2,
        key=key,
    )
    session = FakeSession(None, diagnostic_state, access_state)
    execution, duplicate = await security_access(
        cast(AsyncSession, session),
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is False
    assert execution.result["security_level"] == 1
    assert diagnostic_state.security_level == 1
    assert diagnostic_state.version == 4
    assert access_state.expected_key_digest is None
    assert key not in str(execution.request)
    assert key not in str(execution.result)


@pytest.mark.asyncio
async def test_security_invalid_keys_are_idempotent_and_lock_after_three_attempts() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(), ecu_id=ecu.id, session_type="extended", version=3, simulation_time_ms=2_500
    )
    access_state = security_state(ecu, version=2)
    access_state.expected_key_digest = "0" * 64
    access_state.seed_expires_at_ms = 32_500
    access_state.target_level = 1
    last_execution: DiagnosticCommand | None = None
    for attempt in range(1, 4):
        command = SecurityAccessCommand(
            command_id=f"security-invalid-{attempt}",
            access_type=2,
            expected_session_version=3,
            expected_security_version=attempt + 1,
            key="FFFFFFFFFFFFFFFF",
        )
        session = FakeSession(None, diagnostic_state, access_state)
        with pytest.raises(DiagnosticContractError) as error:
            await security_access(
                cast(AsyncSession, session),
                vehicle=vehicle,
                ecu=ecu,
                command=command,
                actor_user_id=uuid4(),
                correlation_id=None,
            )
        assert error.value.details is not None
        expected_nrc = 0x36 if attempt == 3 else 0x35
        assert error.value.details["negative_response_code"] == expected_nrc
        assert error.value.details["failed_attempts"] == attempt
        last_execution = next(item for item in session.added if isinstance(item, DiagnosticCommand))
        assert "FFFFFFFFFFFFFFFF" not in str(last_execution.request)
    assert access_state.locked_until_ms == 12_500
    assert last_execution is not None

    repeated = SecurityAccessCommand(
        command_id="security-invalid-3",
        access_type=2,
        expected_session_version=3,
        expected_security_version=4,
        key="FFFFFFFFFFFFFFFF",
    )
    with pytest.raises(DiagnosticContractError) as repeated_error:
        await security_access(
            cast(AsyncSession, FakeSession(last_execution)),
            vehicle=vehicle,
            ecu=ecu,
            command=repeated,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert repeated_error.value.details is not None
    assert repeated_error.value.details["failed_attempts"] == 3
    assert access_state.version == 5


@pytest.mark.asyncio
async def test_security_access_enforces_session_sequence_and_logical_lockout() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(), ecu_id=ecu.id, session_type="default", version=1, simulation_time_ms=2_500
    )
    access_state = security_state(ecu)
    seed_command = SecurityAccessCommand(
        command_id="security-default-denied",
        access_type=1,
        expected_session_version=1,
        expected_security_version=1,
    )
    with pytest.raises(DiagnosticContractError) as error:
        await security_access(
            cast(AsyncSession, FakeSession(None, diagnostic_state, access_state)),
            vehicle=vehicle,
            ecu=ecu,
            command=seed_command,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x7F

    diagnostic_state.session_type = "extended"
    send_without_seed = SecurityAccessCommand(
        command_id="security-sequence-denied",
        access_type=2,
        expected_session_version=1,
        expected_security_version=1,
        key="0011223344556677",
    )
    with pytest.raises(DiagnosticContractError) as error:
        await security_access(
            cast(AsyncSession, FakeSession(None, diagnostic_state, access_state)),
            vehicle=vehicle,
            ecu=ecu,
            command=send_without_seed,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x24

    access_state.locked_until_ms = 10_000
    with pytest.raises(DiagnosticContractError) as error:
        await security_access(
            cast(AsyncSession, FakeSession(None, diagnostic_state, access_state)),
            vehicle=vehicle,
            ecu=ecu,
            command=seed_command,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x37

    ecu.simulation_time_ms = 10_000
    execution, _ = await security_access(
        cast(AsyncSession, FakeSession(None, diagnostic_state, access_state)),
        vehicle=vehicle,
        ecu=ecu,
        command=seed_command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert execution.result["accepted"] is True
    assert access_state.failed_attempts == 0


def test_routine_contracts_are_bounded_and_operation_specific() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 600000"):
        RoutineCreate(
            identifier=1,
            name="Unbounded",
            allowed_sessions=["extended"],
            execution_time_ms=600_001,
        )
    with pytest.raises(ValidationError, match="only startRoutine"):
        RoutineControlCommand(
            command_id="routine-invalid-parameters",
            control_type=3,
            expected_session_version=1,
            expected_routine_version=1,
            parameters={"secret": 1},
        )


@pytest.mark.asyncio
async def test_routine_catalogue_is_bounded_audited_and_minimized() -> None:
    vehicle, ecu = vehicle_and_ecu()
    session = FakeSession(None, 0)
    routine, state = await create_routine(
        cast(AsyncSession, session),
        vehicle=vehicle,
        ecu=ecu,
        command=RoutineCreate(
            identifier=0x0201,
            name="Battery cell balancing",
            allowed_sessions=["extended"],
            execution_time_ms=500,
            supports_stop=True,
            result_template={"balanced": True, "delta_mv": 4.2},
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert routine.identifier == 0x0201
    assert state.status == "idle"
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.event_type == "atep.diagnostics.routine.created.v1"
    assert "result_template" not in event.payload
    assert "result_template" not in audit.details

    with pytest.raises(DiagnosticContractError) as error:
        await create_routine(
            cast(AsyncSession, FakeSession(None, 64)),
            vehicle=vehicle,
            ecu=ecu,
            command=RoutineCreate(
                identifier=2,
                name="Bounded",
                allowed_sessions=["extended"],
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["reason"] == "an ECU may define at most 64 routines in V-3"


@pytest.mark.asyncio
async def test_routine_start_is_versioned_idempotent_and_value_minimized() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(), ecu_id=ecu.id, session_type="extended", version=3, simulation_time_ms=0
    )
    routine, routine_state = battery_balance_routine(ecu)
    command = RoutineControlCommand(
        command_id="routine-start-001",
        control_type=1,
        expected_session_version=3,
        expected_routine_version=1,
        parameters={"target_delta_mv": 5.0},
    )
    session = FakeSession(None, diagnostic_state, routine, routine_state)
    execution, duplicate = await control_routine(
        cast(AsyncSession, session),
        vehicle=vehicle,
        ecu=ecu,
        identifier=0x0201,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is False
    assert execution.service_id == 0x31
    assert execution.result["status"] == "running"
    assert routine_state.started_at_ms == 2_500
    assert routine_state.completes_at_ms == 3_000
    assert routine_state.version == 2
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.payload["control_type"] == 1
    assert "parameters" not in event.payload
    assert "result" not in event.payload
    assert "parameters" not in audit.details

    returned, duplicate = await control_routine(
        cast(AsyncSession, FakeSession(execution)),
        vehicle=vehicle,
        ecu=ecu,
        identifier=0x0201,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is execution
    assert duplicate is True
    assert routine_state.version == 2


@pytest.mark.asyncio
async def test_routine_results_complete_on_ecu_logical_time() -> None:
    vehicle, ecu = vehicle_and_ecu()
    ecu.simulation_time_ms = 3_000
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(), ecu_id=ecu.id, session_type="extended", version=3, simulation_time_ms=0
    )
    routine, routine_state = battery_balance_routine(ecu)
    routine_state.status = "running"
    routine_state.invocation_count = 1
    routine_state.started_at_ms = 2_500
    routine_state.completes_at_ms = 3_000
    routine_state.version = 2
    execution, _ = await control_routine(
        cast(AsyncSession, FakeSession(None, diagnostic_state, routine, routine_state)),
        vehicle=vehicle,
        ecu=ecu,
        identifier=0x0201,
        command=RoutineControlCommand(
            command_id="routine-results-001",
            control_type=3,
            expected_session_version=3,
            expected_routine_version=2,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert execution.result["status"] == "completed"
    assert execution.result["result"] == {"balanced": True, "delta_mv": 4.2}
    assert routine_state.version == 3


@pytest.mark.asyncio
async def test_routine_control_enforces_session_and_stop_capability() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(), ecu_id=ecu.id, session_type="default", version=1, simulation_time_ms=0
    )
    routine, routine_state = battery_balance_routine(ecu)
    with pytest.raises(DiagnosticContractError) as error:
        await control_routine(
            cast(AsyncSession, FakeSession(None, diagnostic_state, routine, routine_state)),
            vehicle=vehicle,
            ecu=ecu,
            identifier=0x0201,
            command=RoutineControlCommand(
                command_id="routine-session-denied",
                control_type=1,
                expected_session_version=1,
                expected_routine_version=1,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x7F

    diagnostic_state.session_type = "extended"
    routine.supports_stop = False
    routine_state.status = "running"
    with pytest.raises(DiagnosticContractError) as error:
        await control_routine(
            cast(AsyncSession, FakeSession(None, diagnostic_state, routine, routine_state)),
            vehicle=vehicle,
            ecu=ecu,
            identifier=0x0201,
            command=RoutineControlCommand(
                command_id="routine-stop-unsupported",
                control_type=2,
                expected_session_version=1,
                expected_routine_version=1,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x31


@pytest.mark.asyncio
async def test_routine_stop_uses_logical_time_and_rejects_stale_version() -> None:
    vehicle, ecu = vehicle_and_ecu()
    diagnostic_state = DiagnosticSessionState(
        id=uuid4(), ecu_id=ecu.id, session_type="extended", version=3, simulation_time_ms=0
    )
    routine, routine_state = battery_balance_routine(ecu)
    routine_state.status = "running"
    routine_state.invocation_count = 1
    routine_state.started_at_ms = 2_000
    routine_state.completes_at_ms = 3_000
    routine_state.version = 2

    with pytest.raises(DiagnosticContractError) as error:
        await control_routine(
            cast(AsyncSession, FakeSession(None, diagnostic_state, routine, routine_state)),
            vehicle=vehicle,
            ecu=ecu,
            identifier=0x0201,
            command=RoutineControlCommand(
                command_id="routine-stop-stale",
                control_type=2,
                expected_session_version=3,
                expected_routine_version=1,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x22

    execution, duplicate = await control_routine(
        cast(AsyncSession, FakeSession(None, diagnostic_state, routine, routine_state)),
        vehicle=vehicle,
        ecu=ecu,
        identifier=0x0201,
        command=RoutineControlCommand(
            command_id="routine-stop-001",
            control_type=2,
            expected_session_version=3,
            expected_routine_version=2,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is False
    assert execution.result["status"] == "stopped"
    assert routine_state.stopped_at_ms == 2_500
    assert routine_state.completes_at_ms is None
    assert routine_state.version == 3


@pytest.mark.asyncio
async def test_did_catalogue_is_typed_bounded_audited_and_evented() -> None:
    vehicle, ecu = vehicle_and_ecu()
    session = FakeSession(None, 0)
    did = await create_did(
        cast(AsyncSession, session),
        vehicle=vehicle,
        ecu=ecu,
        command=DidCreate(
            identifier=0xF190,
            name="Battery temperature",
            data_type="decimal",
            unit="celsius",
            writable=True,
            readable_sessions=["default", "extended"],
            writable_sessions=["extended"],
            value=24.5,
            minimum=-40,
            maximum=100,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert did.identifier == 0xF190
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.event_type == "atep.diagnostics.did.created.v1"
    assert event.payload["identifier_hex"] == "0xF190"
    assert "value" not in event.payload
    assert "value" not in audit.details

    with pytest.raises(DiagnosticContractError) as error:
        await create_did(
            cast(AsyncSession, FakeSession(None, 0)),
            vehicle=vehicle,
            ecu=ecu,
            command=DidCreate(
                identifier=1,
                name="Invalid",
                data_type="integer",
                readable_sessions=["default"],
                value="not-an-integer",
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["reason"] == "value does not match DID data type integer"

    with pytest.raises(DiagnosticContractError) as error:
        await create_did(
            cast(AsyncSession, FakeSession(None, 128)),
            vehicle=vehicle,
            ecu=ecu,
            command=DidCreate(
                identifier=2,
                name="Bounded",
                data_type="boolean",
                readable_sessions=["default"],
                value=True,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["reason"] == "an ECU may define at most 128 DIDs in V-2"


@pytest.mark.asyncio
async def test_read_dids_is_session_aware_idempotent_and_minimizes_evidence() -> None:
    vehicle, ecu = vehicle_and_ecu()
    state = DiagnosticSessionState(
        id=uuid4(), ecu_id=ecu.id, session_type="default", version=2, simulation_time_ms=0
    )
    did = writable_temperature_did(ecu)
    command = DidReadCommand(command_id="uds-read-did-001", identifiers=[0xF190])
    session = FakeSession(None, state, did)
    execution, duplicate = await read_dids(
        cast(AsyncSession, session),
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is False
    assert execution.service_id == 0x22
    assert execution.result["items"][0]["value"] == 24.5
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.payload["identifiers"] == [0xF190]
    assert "value" not in event.payload
    assert "value" not in audit.details

    returned, duplicate = await read_dids(
        cast(AsyncSession, FakeSession(execution)),
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is execution
    assert duplicate is True

    did.readable_sessions = ["extended"]
    with pytest.raises(DiagnosticContractError) as error:
        await read_dids(
            cast(AsyncSession, FakeSession(None, state, did)),
            vehicle=vehicle,
            ecu=ecu,
            command=DidReadCommand(command_id="uds-read-did-session", identifiers=[0xF190]),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x7F


@pytest.mark.asyncio
async def test_write_did_requires_session_and_versions_and_validates_range() -> None:
    vehicle, ecu = vehicle_and_ecu()
    state = DiagnosticSessionState(
        id=uuid4(), ecu_id=ecu.id, session_type="extended", version=3, simulation_time_ms=0
    )
    did = writable_temperature_did(ecu)
    session = FakeSession(None, state, did)
    command = DidWriteCommand(
        command_id="uds-write-did-001",
        expected_session_version=3,
        expected_did_version=1,
        value=47.8,
    )
    execution, duplicate = await write_did(
        cast(AsyncSession, session),
        vehicle=vehicle,
        ecu=ecu,
        identifier=0xF190,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is False
    assert execution.service_id == 0x2E
    assert did.value == 47.8
    assert did.version == 2
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert "value" not in event.payload

    returned, duplicate = await write_did(
        cast(AsyncSession, FakeSession(execution)),
        vehicle=vehicle,
        ecu=ecu,
        identifier=0xF190,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is execution
    assert duplicate is True
    assert did.version == 2

    default_state = state
    default_state.session_type = "default"
    with pytest.raises(DiagnosticContractError) as error:
        await write_did(
            cast(AsyncSession, FakeSession(None, default_state, did)),
            vehicle=vehicle,
            ecu=ecu,
            identifier=0xF190,
            command=DidWriteCommand(
                command_id="uds-write-did-default",
                expected_session_version=3,
                expected_did_version=2,
                value=48.0,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["negative_response_code"] == 0x7F

    default_state.session_type = "extended"
    with pytest.raises(DiagnosticContractError) as error:
        await write_did(
            cast(AsyncSession, FakeSession(None, default_state, did)),
            vehicle=vehicle,
            ecu=ecu,
            identifier=0xF190,
            command=DidWriteCommand(
                command_id="uds-write-did-range",
                expected_session_version=3,
                expected_did_version=2,
                value=101.0,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details is not None
    assert error.value.details["reason"] == "value exceeds maximum 100.0"


@pytest.mark.asyncio
async def test_session_control_is_versioned_idempotent_audited_and_evented() -> None:
    vehicle, ecu = vehicle_and_ecu()
    state = DiagnosticSessionState(
        id=uuid4(),
        ecu_id=ecu.id,
        session_type="default",
        security_level=0,
        version=1,
        simulation_time_ms=0,
    )
    security_state = DiagnosticSecurityState(
        id=uuid4(),
        ecu_id=ecu.id,
        challenge_counter=4,
        expected_key_digest="a" * 64,
        seed_expires_at_ms=30_000,
        failed_attempts=2,
        locked_until_ms=10_000,
        target_level=1,
        version=7,
    )
    command = DiagnosticSessionControlCommand(
        command_id="uds-session-001", expected_version=1, session_type="extended"
    )
    session = FakeSession(None, state, security_state)
    execution, duplicate = await control_session(
        cast(AsyncSession, session),
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert execution.service_id == 0x10
    assert execution.result["session_type"] == "extended"
    assert state.version == 2
    assert state.simulation_time_ms == 2_500
    assert security_state.expected_key_digest is None
    assert security_state.seed_expires_at_ms is None
    assert security_state.failed_attempts == 0
    assert security_state.locked_until_ms is None
    assert security_state.target_level == 0
    assert security_state.version == 8
    assert execution.result["security_version"] == 8
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert [item.event_type for item in events] == ["atep.diagnostics.session.changed.v1"]
    assert events[0].payload["positive_response_service_id"] == 0x50
    assert [item.action for item in audits] == ["diagnostics.session_changed"]

    returned, duplicate = await control_session(
        cast(AsyncSession, FakeSession(execution)),
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is execution
    assert duplicate is True

    changed = command.model_copy(update={"session_type": DiagnosticSessionType.PROGRAMMING})
    with pytest.raises(DiagnosticCommandConflictError):
        await control_session(
            cast(AsyncSession, FakeSession(execution)),
            vehicle=vehicle,
            ecu=ecu,
            command=changed,
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_session_control_returns_stable_uds_negative_response() -> None:
    vehicle, ecu = vehicle_and_ecu()
    state = DiagnosticSessionState(
        id=uuid4(),
        ecu_id=ecu.id,
        session_type="default",
        security_level=0,
        version=3,
        simulation_time_ms=0,
    )
    with pytest.raises(DiagnosticContractError) as error:
        await control_session(
            cast(AsyncSession, FakeSession(None, state)),
            vehicle=vehicle,
            ecu=ecu,
            command=DiagnosticSessionControlCommand(
                command_id="uds-session-stale", expected_version=1, session_type="extended"
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details == {
        "reason": "session version is 3",
        "negative_response_code": UdsNegativeResponseCode.CONDITIONS_NOT_CORRECT,
    }


@pytest.mark.asyncio
async def test_dtc_report_uses_logical_time_and_minimized_evidence() -> None:
    vehicle, ecu = vehicle_and_ecu()
    command = DtcReportCommand(
        code="0A80FF",
        status_mask=0x09,
        severity="critical",
        description="Battery pack deterioration",
        snapshot={"soc": 31.5, "pack_temperature": 47.8},
    )
    session = FakeSession(None, 0)
    dtc = await report_dtc(
        cast(AsyncSession, session),
        vehicle=vehicle,
        ecu=ecu,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert isinstance(dtc, DiagnosticTroubleCode)
    assert dtc.first_seen_ms == 2_500
    assert dtc.last_seen_ms == 2_500
    assert dtc.occurrence_count == 1
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.event_type == "atep.diagnostics.dtc.reported.v1"
    assert "snapshot" not in event.payload
    assert "snapshot" not in audit.details


@pytest.mark.asyncio
async def test_repeated_dtc_report_updates_existing_record() -> None:
    vehicle, ecu = vehicle_and_ecu()
    existing = DiagnosticTroubleCode(
        id=uuid4(),
        ecu_id=ecu.id,
        code="0A80FF",
        status_mask=1,
        severity="warning",
        description="",
        occurrence_count=2,
        first_seen_ms=500,
        last_seen_ms=1_000,
        snapshot={},
        version=2,
    )
    updated = await report_dtc(
        cast(AsyncSession, FakeSession(existing)),
        vehicle=vehicle,
        ecu=ecu,
        command=DtcReportCommand(code="0A80FF", status_mask=9, severity="critical"),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert updated is existing
    assert updated.occurrence_count == 3
    assert updated.last_seen_ms == 2_500
    assert updated.version == 3


@pytest.mark.asyncio
async def test_dtc_catalogue_is_bounded_per_ecu() -> None:
    vehicle, ecu = vehicle_and_ecu()
    with pytest.raises(DiagnosticContractError) as error:
        await report_dtc(
            cast(AsyncSession, FakeSession(None, 200)),
            vehicle=vehicle,
            ecu=ecu,
            command=DtcReportCommand(code="0A80FF", status_mask=1),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details == {
        "reason": "an ECU may store at most 200 DTCs in V-1",
        "negative_response_code": UdsNegativeResponseCode.REQUEST_OUT_OF_RANGE,
    }


def test_diagnostic_permissions_are_independent() -> None:
    assert PermissionName.DIAGNOSTICS_READ.value == "diagnostics:read"
    assert PermissionName.DIAGNOSTICS_MANAGE.value == "diagnostics:manage"
    assert require_permissions(PermissionName.DIAGNOSTICS_READ.value) is not None


def test_diagnostic_command_model_preserves_uds_service_identity() -> None:
    command = DiagnosticCommand(
        ecu_id=uuid4(),
        command_id="uds-read-dtc-001",
        service_id=0x19,
        request={},
        result={"count": 0},
        previous_version=1,
        session_version=1,
        requested_by_user_id=uuid4(),
    )
    assert command.service_id + 0x40 == 0x59
