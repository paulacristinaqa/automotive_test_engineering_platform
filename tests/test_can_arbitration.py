from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.can_network.arbitration_service import execute_arbitration
from atep.can_network.models import (
    CanArbitrationExecution,
    CanFrameTransmission,
    CanNetwork,
)
from atep.can_network.schemas import CanArbitrationCommand
from atep.core.errors import (
    CanArbitrationCommandConflictError,
    CanNetworkContractError,
    CanNetworkVersionConflictError,
)
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
    now = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
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


def _network(target: Vehicle, nodes: list[UUID]) -> CanNetwork:
    now = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
    contracts = [
        {
            "identifier": "priority-high",
            "frame_id": 0x100,
            "frame_format": "standard",
            "dlc": 1,
            "producer_node_id": str(nodes[0]),
            "consumer_node_ids": [str(nodes[2])],
        },
        {
            "identifier": "priority-low",
            "frame_id": 0x200,
            "frame_format": "standard",
            "dlc": 2,
            "producer_node_id": str(nodes[1]),
            "consumer_node_ids": [str(nodes[2])],
        },
        {
            "identifier": "extended-equal",
            "frame_id": 0x100,
            "frame_format": "extended",
            "dlc": 0,
            "producer_node_id": str(nodes[1]),
            "consumer_node_ids": [],
        },
    ]
    return CanNetwork(
        id=uuid4(),
        vehicle_id=target.id,
        identifier="powertrain-can",
        display_name="Powertrain CAN",
        bitrate_kbps=500,
        nodes=[{"ecu_id": str(node), "role": "participant"} for node in nodes],
        frame_contracts=contracts,
        version=3,
        simulation_time_us=1_000,
        next_sequence=7,
        created_at=now,
        updated_at=now,
    )


def _command(nodes: list[UUID]) -> CanArbitrationCommand:
    return CanArbitrationCommand(
        command_id="arbitration-001",
        expected_version=3,
        contenders=[
            {
                "contract_id": "priority-low",
                "producer_node_id": nodes[1],
                "payload": [1, 2],
                "ready_offset_us": 0,
            },
            {
                "contract_id": "extended-equal",
                "producer_node_id": nodes[1],
                "payload": [],
                "ready_offset_us": 0,
            },
            {
                "contract_id": "priority-high",
                "producer_node_id": nodes[0],
                "payload": [9],
                "ready_offset_us": 0,
            },
        ],
    )


def test_arbitration_contract_is_bounded_and_rejects_duplicates() -> None:
    node = uuid4()
    with pytest.raises(ValidationError, match="must be unique"):
        CanArbitrationCommand(
            command_id="arbitration-001",
            expected_version=1,
            contenders=[
                {"contract_id": "same-frame", "producer_node_id": node, "payload": []},
                {"contract_id": "same-frame", "producer_node_id": node, "payload": []},
            ],
        )
    with pytest.raises(ValidationError):
        CanArbitrationCommand(
            command_id="arbitration-001",
            expected_version=1,
            contenders=[
                {
                    "contract_id": f"frame-{index}",
                    "producer_node_id": node,
                    "payload": [],
                }
                for index in range(65)
            ],
        )


@pytest.mark.asyncio
async def test_arbitration_prioritizes_id_then_format_and_records_delivery() -> None:
    target = _vehicle()
    nodes = [uuid4(), uuid4(), uuid4()]
    bus = _network(target, nodes)
    session = FakeSession([bus, None])
    execution, updated, duplicate = await execute_arbitration(
        cast(AsyncSession, session),
        vehicle=target,
        command=_command(nodes),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert not duplicate
    frames = execution.result["frames"]
    assert [frame["contract_id"] for frame in frames] == [
        "priority-high",
        "extended-equal",
        "priority-low",
    ]
    assert [frame["bit_count"] for frame in frames] == [55, 67, 63]
    assert [frame["duration_us"] for frame in frames] == [110, 134, 126]
    assert frames[0]["deliveries"][0]["received_at_us"] == 1_110
    assert frames[0]["deliveries"][0]["latency_us"] == 110
    assert updated.simulation_time_us == 1_370
    assert updated.next_sequence == 10
    assert updated.version == 4
    utilization = execution.result["utilization"]
    assert utilization == {
        "window_start_us": 1_000,
        "window_end_us": 1_370,
        "window_duration_us": 370,
        "occupied_us": 370,
        "idle_us": 0,
        "utilization_percent": 100.0,
        "maximum_latency_us": 370,
    }
    transmissions = [item for item in session.added if isinstance(item, CanFrameTransmission)]
    assert [item.payload for item in transmissions] == [[9], [], [1, 2]]
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.event_type == "atep.can.arbitration.completed.v1"
    assert "payload" not in event.payload
    assert "payload" not in audit.details


@pytest.mark.asyncio
async def test_arbitration_advances_to_next_ready_time_and_measures_idle_bus() -> None:
    target = _vehicle()
    nodes = [uuid4(), uuid4(), uuid4()]
    bus = _network(target, nodes)
    command = _command(nodes).model_copy(
        update={
            "contenders": [
                _command(nodes).contenders[0].model_copy(update={"ready_offset_us": 50})
            ]
        }
    )
    execution, _, _ = await execute_arbitration(
        cast(AsyncSession, FakeSession([bus, None])),
        vehicle=target,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    utilization = execution.result["utilization"]
    assert utilization["idle_us"] == 50
    assert utilization["occupied_us"] == 126
    assert utilization["window_duration_us"] == 176
    assert utilization["utilization_percent"] == 71.5909


@pytest.mark.asyncio
async def test_arbitration_replay_conflict_version_and_contract_validation() -> None:
    target = _vehicle()
    nodes = [uuid4(), uuid4(), uuid4()]
    bus = _network(target, nodes)
    command = _command(nodes)
    existing = CanArbitrationExecution(
        id=uuid4(),
        network_id=bus.id,
        command_id=command.command_id,
        request=command.model_dump(mode="json"),
        result={"frames": [], "utilization": {}},
        contender_count=3,
        previous_version=3,
        network_version=4,
        requested_by_user_id=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    replay = await execute_arbitration(
        cast(AsyncSession, FakeSession([bus, existing])),
        vehicle=target,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert replay[2]
    with pytest.raises(CanArbitrationCommandConflictError):
        await execute_arbitration(
            cast(AsyncSession, FakeSession([bus, existing])),
            vehicle=target,
            command=command.model_copy(update={"expected_version": 2}),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    with pytest.raises(CanNetworkVersionConflictError):
        await execute_arbitration(
            cast(AsyncSession, FakeSession([bus, None])),
            vehicle=target,
            command=command.model_copy(update={"expected_version": 2}),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    bad_producer = command.model_copy(
        update={
            "contenders": [
                command.contenders[0].model_copy(update={"producer_node_id": uuid4()})
            ]
        }
    )
    with pytest.raises(CanNetworkContractError) as producer_conflict:
        await execute_arbitration(
            cast(AsyncSession, FakeSession([bus, None])),
            vehicle=target,
            command=bad_producer,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    details = cast(dict[str, Any], producer_conflict.value.details)
    assert "declared producer" in details["reason"]


def test_arbitration_model_preserves_request_result_and_versions() -> None:
    assert {
        "request",
        "result",
        "contender_count",
        "previous_version",
        "network_version",
    } <= set(CanArbitrationExecution.__table__.columns.keys())
