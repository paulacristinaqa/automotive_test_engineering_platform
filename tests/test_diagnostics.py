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
    DiagnosticSessionState,
    DiagnosticTroubleCode,
)
from atep.diagnostics.schemas import (
    DiagnosticSessionControlCommand,
    DiagnosticSessionType,
    DidCreate,
    DidReadCommand,
    DidWriteCommand,
    DtcReportCommand,
    UdsNegativeResponseCode,
)
from atep.diagnostics.service import control_session, create_did, read_dids, report_dtc, write_did
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
    command = DiagnosticSessionControlCommand(
        command_id="uds-session-001", expected_version=1, session_type="extended"
    )
    session = FakeSession(None, state)
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
