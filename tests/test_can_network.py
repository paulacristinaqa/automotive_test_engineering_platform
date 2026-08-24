from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.can_network.models import CanFrameTransmission, CanNetwork
from atep.can_network.schemas import CanFrameSubmitCommand, CanNetworkCreate
from atep.can_network.service import create_can_network, submit_can_frame
from atep.core.errors import (
    CanFrameCommandConflictError,
    CanNetworkContractError,
    CanNetworkVersionConflictError,
)
from atep.events.models import OutboxEvent
from atep.identity.permissions import PermissionName
from atep.vehicles.models import Vehicle


class ScalarResult:
    def __init__(self, values: list[Any]) -> None:
        self.values = values

    def scalars(self) -> "ScalarResult":
        return self

    def all(self) -> list[Any]:
        return self.values


class FakeSession:
    def __init__(
        self,
        *,
        scalar_values: list[Any] | None = None,
        execute_values: list[list[Any]] | None = None,
    ) -> None:
        self.scalar_values = list(scalar_values or [])
        self.execute_values = list(execute_values or [])
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def execute(self, _: Any) -> ScalarResult:
        return ScalarResult(self.execute_values.pop(0) if self.execute_values else [])

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    def begin_nested(self) -> Any:
        class Transaction:
            async def __aenter__(self) -> None:
                return None

            async def __aexit__(self, *_: object) -> None:
                return None

        return Transaction()


def vehicle() -> Vehicle:
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


def command(ecu_id: Any) -> CanNetworkCreate:
    return CanNetworkCreate(
        identifier="powertrain-can",
        display_name="Powertrain CAN",
        bitrate_kbps=500,
        nodes=[{"ecu_id": ecu_id, "role": "participant"}],
        frame_contracts=[
            {
                "identifier": "bms-status",
                "frame_id": 0x180,
                "frame_format": "standard",
                "dlc": 2,
                "producer_node_id": ecu_id,
            }
        ],
    )


def network(target: Vehicle, ecu_id: Any) -> CanNetwork:
    now = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
    return CanNetwork(
        id=uuid4(),
        vehicle_id=target.id,
        identifier="powertrain-can",
        display_name="Powertrain CAN",
        bitrate_kbps=500,
        nodes=[{"ecu_id": str(ecu_id), "role": "participant"}],
        frame_contracts=[
            {
                "identifier": "bms-status",
                "frame_id": 384,
                "frame_format": "standard",
                "dlc": 2,
                "producer_node_id": str(ecu_id),
                "consumer_node_ids": [],
            }
        ],
        version=1,
        simulation_time_us=0,
        next_sequence=1,
        created_at=now,
        updated_at=now,
    )


def test_can_contract_bounds_and_topology_validation() -> None:
    ecu_id = uuid4()
    with pytest.raises(ValidationError, match="at most 0x7FF"):
        CanNetworkCreate(
            identifier="can-a",
            display_name="CAN A",
            nodes=[{"ecu_id": ecu_id}],
            frame_contracts=[
                {"identifier": "bad-id", "frame_id": 0x800, "dlc": 1, "producer_node_id": ecu_id}
            ],
        )
    with pytest.raises(ValidationError, match="declared nodes"):
        CanNetworkCreate(
            identifier="can-a",
            display_name="CAN A",
            nodes=[{"ecu_id": ecu_id}],
            frame_contracts=[
                {"identifier": "bad-node", "frame_id": 1, "dlc": 1, "producer_node_id": uuid4()}
            ],
        )
    with pytest.raises(ValidationError):
        CanNetworkCreate(
            identifier="can-a", display_name="CAN A", nodes=[{"ecu_id": uuid4()} for _ in range(65)]
        )
    with pytest.raises(ValidationError, match="between 0 and 255"):
        CanFrameSubmitCommand(
            command_id="command-001",
            expected_version=1,
            contract_id="bms-status",
            producer_node_id=ecu_id,
            payload=[256],
        )


@pytest.mark.asyncio
async def test_network_creation_is_bounded_audited_and_evented() -> None:
    target = vehicle()
    ecu_id = uuid4()
    session = FakeSession(scalar_values=[None], execute_values=[[ecu_id]])
    created = await create_can_network(
        cast(AsyncSession, session),
        vehicle=target,
        command=command(ecu_id),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert created.version == 1
    assert created.next_sequence == 1
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.event_type == "atep.can.network.created.v1"
    assert event.payload["node_count"] == 1
    assert "nodes" not in event.payload
    assert audit.action == "can.network_created"


@pytest.mark.asyncio
async def test_frame_submission_is_deterministic_versioned_and_minimized() -> None:
    target = vehicle()
    ecu_id = uuid4()
    bus = network(target, ecu_id)
    session = FakeSession(scalar_values=[bus, None])
    request = CanFrameSubmitCommand(
        command_id="frame-command-001",
        expected_version=1,
        contract_id="bms-status",
        producer_node_id=ecu_id,
        payload=[10, 20],
        advance_time_us=250,
    )
    item, updated, duplicate = await submit_can_frame(
        cast(AsyncSession, session),
        vehicle=target,
        command=request,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert not duplicate
    assert item.sequence == 1
    assert item.transmission_time_us == 250
    assert updated.version == 2
    assert updated.next_sequence == 2
    event = next(value for value in session.added if isinstance(value, OutboxEvent))
    audit = next(value for value in session.added if isinstance(value, AuditRecord))
    assert event.event_type == "atep.can.frame.submitted.v1"
    assert "payload" not in event.payload
    assert "payload" not in audit.details


@pytest.mark.asyncio
async def test_frame_exact_replay_and_changed_reuse_are_distinct() -> None:
    target = vehicle()
    ecu_id = uuid4()
    bus = network(target, ecu_id)
    request = CanFrameSubmitCommand(
        command_id="frame-command-001",
        expected_version=1,
        contract_id="bms-status",
        producer_node_id=ecu_id,
        payload=[10, 20],
        advance_time_us=250,
    )
    existing = CanFrameTransmission(
        id=uuid4(),
        network_id=bus.id,
        command_id=request.command_id,
        contract_id=request.contract_id,
        producer_node_id=ecu_id,
        frame_id=384,
        frame_format="standard",
        request=request.model_dump(mode="json"),
        payload=[10, 20],
        sequence=1,
        transmission_time_us=250,
        previous_version=1,
        network_version=2,
        requested_by_user_id=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    bus.version = 2
    replay_session = FakeSession(scalar_values=[bus, existing])
    assert (
        await submit_can_frame(
            cast(AsyncSession, replay_session),
            vehicle=target,
            command=request,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    )[2]
    changed = request.model_copy(update={"payload": [11, 20]})
    conflict_session = FakeSession(scalar_values=[bus, existing])
    with pytest.raises(CanFrameCommandConflictError):
        await submit_can_frame(
            cast(AsyncSession, conflict_session),
            vehicle=target,
            command=changed,
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_frame_submission_rejects_version_producer_and_dlc_conflicts() -> None:
    target = vehicle()
    ecu_id = uuid4()
    bus = network(target, ecu_id)
    base = CanFrameSubmitCommand(
        command_id="frame-command-001",
        expected_version=1,
        contract_id="bms-status",
        producer_node_id=ecu_id,
        payload=[1, 2],
    )
    with pytest.raises(CanNetworkVersionConflictError):
        await submit_can_frame(
            cast(AsyncSession, FakeSession(scalar_values=[bus, None])),
            vehicle=target,
            command=base.model_copy(update={"expected_version": 2}),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    with pytest.raises(CanNetworkContractError) as producer_conflict:
        await submit_can_frame(
            cast(AsyncSession, FakeSession(scalar_values=[bus, None])),
            vehicle=target,
            command=base.model_copy(update={"producer_node_id": uuid4()}),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert "producer" in producer_conflict.value.details["reason"]
    with pytest.raises(CanNetworkContractError) as dlc_conflict:
        await submit_can_frame(
            cast(AsyncSession, FakeSession(scalar_values=[bus, None])),
            vehicle=target,
            command=base.model_copy(update={"payload": [1]}),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert "DLC" in dlc_conflict.value.details["reason"]


def test_can_permissions_are_independent() -> None:
    assert PermissionName.CAN_NETWORKS_READ.value == "can_networks:read"
    assert PermissionName.CAN_NETWORKS_MANAGE.value == "can_networks:manage"


def test_can_models_expose_bounded_persistence_columns() -> None:
    assert {"nodes", "frame_contracts", "version", "simulation_time_us"} <= set(
        CanNetwork.__table__.columns.keys()
    )
    assert {"request", "payload", "sequence", "network_version"} <= set(
        CanFrameTransmission.__table__.columns.keys()
    )
