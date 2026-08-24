from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.can_network.arbitration_service import execute_arbitration, frame_timing
from atep.can_network.dbc_service import decode_message, encode_message
from atep.can_network.models import CanFrameTransmission, CanNetwork
from atep.can_network.schemas import (
    CanArbitrationCommand,
    CanDbcMessage,
    CanFrameContract,
    CanFrameSubmitCommand,
    CanNetworkCreate,
)
from atep.can_network.service import submit_can_frame
from atep.core.errors import CanNetworkContractError
from atep.events.models import OutboxEvent
from atep.vehicles.models import Vehicle


class FakeSession:
    def __init__(self, scalar_values: list[Any]) -> None:
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


def _vehicle() -> Vehicle:
    now = datetime(2026, 8, 24, 20, 0, tzinfo=UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="Reference EV",
        model="EV",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def _fd_network(target: Vehicle, nodes: list[UUID]) -> CanNetwork:
    now = datetime(2026, 8, 24, 20, 0, tzinfo=UTC)
    return CanNetwork(
        id=uuid4(),
        vehicle_id=target.id,
        identifier="powertrain-fd",
        display_name="Powertrain CAN FD",
        bitrate_kbps=500,
        can_fd_enabled=True,
        data_bitrate_kbps=2000,
        nodes=[{"ecu_id": str(node), "role": "participant"} for node in nodes],
        frame_contracts=[
            {
                "identifier": "classic-heartbeat",
                "frame_id": 0x200,
                "frame_format": "standard",
                "protocol": "classic",
                "dlc": 8,
                "bitrate_switch": False,
                "producer_node_id": str(nodes[0]),
                "consumer_node_ids": [str(nodes[1])],
            },
            {
                "identifier": "fd-battery-block",
                "frame_id": 0x100,
                "frame_format": "standard",
                "protocol": "fd",
                "dlc": 64,
                "bitrate_switch": True,
                "producer_node_id": str(nodes[1]),
                "consumer_node_ids": [str(nodes[0])],
            },
        ],
        version=4,
        simulation_time_us=1_000,
        next_sequence=10,
        created_at=now,
        updated_at=now,
    )


def test_can_fd_schema_enforces_network_and_iso_payload_rules() -> None:
    node = uuid4()
    base = {
        "identifier": "fd-frame",
        "frame_id": 0x100,
        "protocol": "fd",
        "producer_node_id": node,
    }
    with pytest.raises(ValidationError, match="ISO-defined"):
        CanFrameContract(**base, dlc=10)
    with pytest.raises(ValidationError, match="only for CAN FD"):
        CanFrameContract(**(base | {"protocol": "classic"}), dlc=8, bitrate_switch=True)
    with pytest.raises(ValidationError, match="require a CAN FD-enabled"):
        CanNetworkCreate(
            identifier="classic-can",
            display_name="Classic CAN",
            nodes=[{"ecu_id": node}],
            frame_contracts=[CanFrameContract(**base, dlc=12)],
        )
    with pytest.raises(ValidationError, match="require a data bitrate"):
        CanNetworkCreate(
            identifier="fd-can",
            display_name="CAN FD",
            can_fd_enabled=True,
            nodes=[{"ecu_id": node}],
        )


def test_can_fd_schema_accepts_mixed_classic_and_fd_contracts() -> None:
    nodes = [uuid4(), uuid4()]
    network = CanNetworkCreate(
        identifier="mixed-can",
        display_name="Mixed CAN and CAN FD",
        bitrate_kbps=500,
        can_fd_enabled=True,
        data_bitrate_kbps=2000,
        nodes=[{"ecu_id": node} for node in nodes],
        frame_contracts=[
            {
                "identifier": "classic-frame",
                "frame_id": 0x200,
                "dlc": 8,
                "producer_node_id": nodes[0],
            },
            {
                "identifier": "fd-frame",
                "frame_id": 0x100,
                "protocol": "fd",
                "dlc": 64,
                "bitrate_switch": True,
                "producer_node_id": nodes[1],
            },
        ],
    )
    assert network.frame_contracts[0].protocol.value == "classic"
    assert network.frame_contracts[1].protocol.value == "fd"


def test_can_fd_timing_separates_nominal_and_data_phases() -> None:
    target = _vehicle()
    nodes = [uuid4(), uuid4()]
    network = _fd_network(target, nodes)
    contract = CanFrameContract.model_validate(network.frame_contracts[1])
    timing = frame_timing(contract, network)
    assert timing.bit_count == 565
    assert timing.nominal_bit_count == 32
    assert timing.data_bit_count == 533
    assert timing.nominal_phase_duration_us == 64
    assert timing.data_phase_duration_us == 267
    assert timing.duration_us == 331


@pytest.mark.asyncio
async def test_mixed_arbitration_uses_identifier_priority_and_fd_timing() -> None:
    target = _vehicle()
    nodes = [uuid4(), uuid4()]
    network = _fd_network(target, nodes)
    command = CanArbitrationCommand(
        command_id="mixed-arbitration-001",
        expected_version=4,
        contenders=[
            {
                "contract_id": "classic-heartbeat",
                "producer_node_id": nodes[0],
                "payload": list(range(8)),
            },
            {
                "contract_id": "fd-battery-block",
                "producer_node_id": nodes[1],
                "payload": list(range(64)),
            },
        ],
    )
    session = FakeSession([network, None])
    execution, updated, duplicate = await execute_arbitration(
        cast(AsyncSession, session),
        vehicle=target,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert not duplicate
    frames = execution.result["frames"]
    assert [item["protocol"] for item in frames] == ["fd", "classic"]
    assert frames[0]["duration_us"] == 331
    assert frames[1]["duration_us"] == 222
    assert updated.simulation_time_us == 1_553
    transmissions = [item for item in session.added if isinstance(item, CanFrameTransmission)]
    assert transmissions[0].protocol == "fd"
    assert transmissions[0].bitrate_switch is True
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.payload["fd_frame_count"] == 1
    assert event.payload["bitrate_switched_frame_count"] == 1
    assert "payload" not in event.payload
    assert "payload" not in audit.details


@pytest.mark.asyncio
async def test_submit_fd_frame_persists_protocol_and_supports_replay() -> None:
    target = _vehicle()
    nodes = [uuid4(), uuid4()]
    network = _fd_network(target, nodes)
    command = CanFrameSubmitCommand(
        command_id="fd-submit-001",
        expected_version=4,
        contract_id="fd-battery-block",
        producer_node_id=nodes[1],
        payload=list(range(64)),
    )
    session = FakeSession([network, None])
    transmission, updated, duplicate = await submit_can_frame(
        cast(AsyncSession, session),
        vehicle=target,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert not duplicate
    assert transmission.protocol == "fd"
    assert transmission.bitrate_switch is True
    assert len(transmission.payload) == 64
    assert updated.version == 5
    replay = await submit_can_frame(
        cast(AsyncSession, FakeSession([network, transmission])),
        vehicle=target,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert replay[2]


@pytest.mark.asyncio
async def test_fd_payload_must_match_contract_length() -> None:
    target = _vehicle()
    nodes = [uuid4(), uuid4()]
    network = _fd_network(target, nodes)
    with pytest.raises(CanNetworkContractError) as exc_info:
        await submit_can_frame(
            cast(AsyncSession, FakeSession([network, None])),
            vehicle=target,
            command=CanFrameSubmitCommand(
                command_id="fd-submit-short",
                expected_version=4,
                contract_id="fd-battery-block",
                producer_node_id=nodes[1],
                payload=[0] * 48,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert exc_info.value.details == {
        "reason": "payload length must equal the frame contract DLC"
    }


def test_dbc_codec_supports_signals_at_end_of_64_byte_fd_payload() -> None:
    message = CanDbcMessage(
        contract_id="fd-battery-block",
        signals=[
            {
                "identifier": "TailCounter",
                "start_bit": 504,
                "bit_length": 8,
                "byte_order": "intel",
            }
        ],
    )
    payload, raw, physical = encode_message(
        message, dlc=64, values={"TailCounter": Decimal(165)}
    )
    assert len(payload) == 64
    assert payload[-1] == 165
    assert raw == {"TailCounter": 165}
    assert decode_message(message, payload=payload)[1] == physical
