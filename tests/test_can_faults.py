from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.can_network.arbitration_service import execute_arbitration
from atep.can_network.error_state import derive_error_mode
from atep.can_network.fault_service import inject_fault, recover_node
from atep.can_network.models import CanFaultExecution, CanNetwork
from atep.can_network.schemas import (
    CanArbitrationCommand,
    CanBusRecoveryCommand,
    CanFaultInjectionCommand,
    CanFrameSubmitCommand,
    CanNodeErrorMode,
)
from atep.can_network.service import submit_can_frame
from atep.core.errors import CanFaultCommandConflictError, CanFaultStateError, CanNodeBusOffError
from atep.events.models import OutboxEvent
from atep.vehicles.models import Vehicle


class FakeSession:
    def __init__(self, values: list[Any]) -> None:
        self.values = list(values)
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.values.pop(0) if self.values else None

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()


def context() -> tuple[Vehicle, CanNetwork, UUID, UUID]:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    producer, consumer = uuid4(), uuid4()
    vehicle = Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="EV",
        model="EV",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )
    network = CanNetwork(
        id=uuid4(),
        vehicle_id=vehicle.id,
        identifier="powertrain-can",
        display_name="Powertrain CAN",
        bitrate_kbps=500,
        can_fd_enabled=False,
        data_bitrate_kbps=None,
        nodes=[
            {"ecu_id": str(producer), "role": "participant"},
            {"ecu_id": str(consumer), "role": "participant"},
        ],
        frame_contracts=[
            {
                "identifier": "bms-status",
                "frame_id": 384,
                "frame_format": "standard",
                "protocol": "classic",
                "dlc": 2,
                "bitrate_switch": False,
                "producer_node_id": str(producer),
                "consumer_node_ids": [str(consumer)],
            }
        ],
        error_states={},
        version=1,
        simulation_time_us=0,
        next_sequence=1,
        created_at=now,
        updated_at=now,
    )
    return vehicle, network, producer, consumer


def injection(
    node: UUID, *, occurrences: int = 1, fault_type: str = "transmission_error"
) -> CanFaultInjectionCommand:
    return CanFaultInjectionCommand(
        command_id="fault-command-001",
        expected_version=1,
        contract_id="bms-status",
        target_node_id=node,
        fault_type=fault_type,
        occurrences=occurrences,
    )


def test_error_confinement_thresholds_and_command_bounds() -> None:
    assert derive_error_mode(127, 127) is CanNodeErrorMode.ERROR_ACTIVE
    assert derive_error_mode(128, 0) is CanNodeErrorMode.ERROR_PASSIVE
    assert derive_error_mode(0, 128) is CanNodeErrorMode.ERROR_PASSIVE
    assert derive_error_mode(256, 0) is CanNodeErrorMode.BUS_OFF
    _, _, producer, _ = context()
    with pytest.raises(ValidationError):
        injection(producer, occurrences=33)
    with pytest.raises(ValidationError):
        CanBusRecoveryCommand(
            command_id="recover-command-001",
            expected_version=1,
            target_node_id=producer,
            recessive_sequences=127,
        )


@pytest.mark.asyncio
async def test_transmission_fault_reaches_bus_off_and_is_evidenced() -> None:
    vehicle, network, producer, _ = context()
    session = FakeSession([network, None])
    item, updated, duplicate = await inject_fault(
        cast(AsyncSession, session),
        vehicle=vehicle,
        command=injection(producer, occurrences=32),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert not duplicate
    assert item.result["after"] == {
        "transmit_error_count": 256,
        "receive_error_count": 0,
        "state": "bus_off",
    }
    assert item.result["elapsed_us"] == 896
    assert updated.version == 2
    assert updated.next_sequence == 1
    event = next(value for value in session.added if isinstance(value, OutboxEvent))
    audit = next(value for value in session.added if isinstance(value, AuditRecord))
    assert event.event_type == "atep.can.fault.injected.v1"
    assert "request" not in event.payload
    assert audit.action == "can.fault_injected"


@pytest.mark.asyncio
async def test_frame_loss_does_not_change_error_counters() -> None:
    vehicle, network, _, consumer = context()
    session = FakeSession([network, None])
    item, _, _ = await inject_fault(
        cast(AsyncSession, session),
        vehicle=vehicle,
        command=injection(consumer, occurrences=3, fault_type="frame_loss"),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert item.result["lost_frames"] == 3
    assert item.result["error_frames"] == 0
    assert item.result["before"] == item.result["after"]


@pytest.mark.asyncio
async def test_bus_off_recovery_requires_128_sequences_and_resets_counters() -> None:
    vehicle, network, producer, _ = context()
    network.error_states = {
        str(producer): {"transmit_error_count": 256, "receive_error_count": 0, "state": "bus_off"}
    }
    session = FakeSession([network, None])
    command = CanBusRecoveryCommand(
        command_id="recover-command-001",
        expected_version=1,
        target_node_id=producer,
        recessive_sequences=128,
    )
    item, _, _ = await recover_node(
        cast(AsyncSession, session),
        vehicle=vehicle,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert item.result["elapsed_us"] == 2816
    assert item.result["after"]["state"] == "error_active"
    event = next(value for value in session.added if isinstance(value, OutboxEvent))
    assert event.event_type == "atep.can.bus.recovered.v1"


@pytest.mark.asyncio
async def test_recovery_rejects_active_node_and_idempotency_reuse_is_stable() -> None:
    vehicle, network, producer, _ = context()
    command = CanBusRecoveryCommand(
        command_id="recover-command-001",
        expected_version=1,
        target_node_id=producer,
    )
    with pytest.raises(CanFaultStateError):
        await recover_node(
            cast(AsyncSession, FakeSession([network, None])),
            vehicle=vehicle,
            command=command,
            actor_user_id=uuid4(),
            correlation_id=None,
        )

    request = injection(producer)
    existing = CanFaultExecution(
        id=uuid4(),
        network_id=network.id,
        command_id=request.command_id,
        operation="inject",
        target_node_id=producer,
        request=request.model_dump(mode="json"),
        result={},
        previous_version=1,
        network_version=2,
        requested_by_user_id=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert (
        await inject_fault(
            cast(AsyncSession, FakeSession([network, existing])),
            vehicle=vehicle,
            command=request,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    )[2]
    changed = request.model_copy(update={"occurrences": 2})
    with pytest.raises(CanFaultCommandConflictError):
        await inject_fault(
            cast(AsyncSession, FakeSession([network, existing])),
            vehicle=vehicle,
            command=changed,
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_bus_off_node_cannot_submit_or_contend() -> None:
    vehicle, network, producer, _ = context()
    network.error_states = {
        str(producer): {
            "transmit_error_count": 256,
            "receive_error_count": 0,
            "state": "bus_off",
        }
    }
    frame = CanFrameSubmitCommand(
        command_id="frame-command-001",
        expected_version=1,
        contract_id="bms-status",
        producer_node_id=producer,
        payload=[1, 2],
    )
    with pytest.raises(CanNodeBusOffError):
        await submit_can_frame(
            cast(AsyncSession, FakeSession([network, None])),
            vehicle=vehicle,
            command=frame,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    arbitration = CanArbitrationCommand(
        command_id="arbitration-001",
        expected_version=1,
        contenders=[{"contract_id": "bms-status", "producer_node_id": producer, "payload": [1, 2]}],
    )
    with pytest.raises(CanNodeBusOffError):
        await execute_arbitration(
            cast(AsyncSession, FakeSession([network, None])),
            vehicle=vehicle,
            command=arbitration,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
