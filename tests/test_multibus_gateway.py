from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.can_network.models import (
    CanNetwork,
    MultiBusGatewayExecution,
)
from atep.can_network.multibus_service import (
    configure_multibus,
    execute_gateway_route,
    execute_multibus_campaign,
)
from atep.can_network.schemas import (
    GatewayRouteCommand,
    MultiBusCampaignCommand,
    MultiBusCampaignFault,
    MultiBusConfigurationCommand,
)
from atep.core.errors import (
    MultiBusCampaignCommandConflictError,
    MultiBusCampaignContractError,
    MultiBusGatewayCommandConflictError,
    MultiBusGatewayContractError,
)
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


def context() -> tuple[Vehicle, CanNetwork, UUID, UUID, UUID]:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    gateway, producer, consumer = uuid4(), uuid4(), uuid4()
    vehicle = Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="Reference EV",
        model="EV",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )
    network = CanNetwork(
        id=uuid4(),
        vehicle_id=vehicle.id,
        identifier="vehicle-network",
        display_name="Vehicle Network",
        bitrate_kbps=500,
        can_fd_enabled=False,
        data_bitrate_kbps=None,
        nodes=[
            {"ecu_id": str(gateway), "role": "gateway"},
            {"ecu_id": str(producer), "role": "participant"},
            {"ecu_id": str(consumer), "role": "participant"},
        ],
        frame_contracts=[
            {
                "identifier": "can-status",
                "frame_id": 256,
                "frame_format": "standard",
                "protocol": "classic",
                "dlc": 2,
                "bitrate_switch": False,
                "producer_node_id": str(producer),
                "consumer_node_ids": [str(gateway)],
            }
        ],
        error_states={},
        lin_channels=[],
        ethernet_segments=[],
        gateway_routes=[],
        version=1,
        simulation_time_us=100,
        next_sequence=7,
        created_at=now,
        updated_at=now,
    )
    return vehicle, network, gateway, producer, consumer


def configuration(gateway: UUID, producer: UUID, consumer: UUID) -> MultiBusConfigurationCommand:
    return MultiBusConfigurationCommand(
        command_id="multibus-config-001",
        expected_version=1,
        lin_channels=[
            {
                "identifier": "body-lin",
                "bitrate_kbps": 20,
                "master_node_id": gateway,
                "frames": [
                    {
                        "identifier": "lin-status",
                        "frame_id": 18,
                        "publisher_node_id": gateway,
                        "subscriber_node_ids": [consumer],
                        "payload_length": 2,
                        "checksum_model": "enhanced",
                    }
                ],
            }
        ],
        ethernet_segments=[
            {
                "identifier": "vehicle-ethernet",
                "speed_mbps": 100,
                "messages": [
                    {
                        "identifier": "ethernet-status",
                        "ether_type": 0x88B5,
                        "source_node_id": gateway,
                        "destination_node_ids": [consumer],
                        "payload_length": 2,
                        "vlan_id": 10,
                    }
                ],
            }
        ],
        gateway_routes=[
            {
                "identifier": "can-to-lin",
                "gateway_node_id": gateway,
                "source_protocol": "can",
                "source_contract_id": "can-status",
                "destination_protocol": "lin",
                "destination_contract_id": "lin-status",
            },
            {
                "identifier": "lin-to-ethernet",
                "gateway_node_id": gateway,
                "source_protocol": "lin",
                "source_contract_id": "lin-status",
                "destination_protocol": "ethernet",
                "destination_contract_id": "ethernet-status",
            },
        ],
    )


def configured_context() -> tuple[Vehicle, CanNetwork, UUID, UUID, UUID]:
    vehicle, network, gateway, producer, consumer = context()
    config = configuration(gateway, producer, consumer)
    network.lin_channels = [item.model_dump(mode="json") for item in config.lin_channels]
    network.ethernet_segments = [item.model_dump(mode="json") for item in config.ethernet_segments]
    network.gateway_routes = [item.model_dump(mode="json") for item in config.gateway_routes]
    return vehicle, network, gateway, producer, consumer


def campaign(*, expected_version: int = 1) -> MultiBusCampaignCommand:
    return MultiBusCampaignCommand(
        command_id="campaign-command-001",
        expected_version=expected_version,
        steps=[
            {
                "identifier": "battery-to-lin",
                "route_id": "can-to-lin",
                "payload": [10, 20],
                "advance_time_us": 50,
                "latency_budget_us": 4_000,
            },
            {
                "identifier": "lin-to-cloud",
                "route_id": "lin-to-ethernet",
                "payload": [10, 20],
                "advance_time_us": 25,
                "latency_budget_us": 3,
            },
        ],
    )


def test_protocol_contracts_are_bounded() -> None:
    _, _, gateway, producer, consumer = context()
    data = configuration(gateway, producer, consumer).model_dump(mode="json")
    data["lin_channels"][0]["bitrate_kbps"] = 21
    with pytest.raises(ValidationError):
        MultiBusConfigurationCommand.model_validate(data)
    data = configuration(gateway, producer, consumer).model_dump(mode="json")
    data["ethernet_segments"][0]["speed_mbps"] = 200
    with pytest.raises(ValidationError, match="100 or 1000"):
        MultiBusConfigurationCommand.model_validate(data)
    with pytest.raises(ValidationError):
        GatewayRouteCommand(
            command_id="route-command-001",
            expected_version=1,
            route_id="can-to-lin",
            payload=[0] * 1501,
        )


@pytest.mark.asyncio
async def test_configuration_is_versioned_audited_and_evented() -> None:
    vehicle, network, gateway, producer, consumer = context()
    session = FakeSession([network, None])
    execution, updated, duplicate = await configure_multibus(
        cast(AsyncSession, session),
        vehicle=vehicle,
        command=configuration(gateway, producer, consumer),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert not duplicate
    assert execution.result == {
        "lin_channel_count": 1,
        "lin_frame_count": 1,
        "ethernet_segment_count": 1,
        "ethernet_message_count": 1,
        "gateway_route_count": 2,
    }
    assert updated.version == 2
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.event_type == "atep.vehicle.multibus.configured.v1"
    assert "lin_channels" not in event.payload
    assert audit.action == "vehicle.multibus_configured"


@pytest.mark.asyncio
async def test_configuration_requires_gateway_role() -> None:
    vehicle, network, gateway, producer, consumer = context()
    network.nodes[0]["role"] = "participant"
    with pytest.raises(MultiBusGatewayContractError, match="gateway"):
        await configure_multibus(
            cast(AsyncSession, FakeSession([network, None])),
            vehicle=vehicle,
            command=configuration(gateway, producer, consumer),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_can_to_lin_route_has_deterministic_time_and_sequence() -> None:
    vehicle, network, gateway, producer, consumer = context()
    config = configuration(gateway, producer, consumer)
    network.lin_channels = [item.model_dump(mode="json") for item in config.lin_channels]
    network.ethernet_segments = [item.model_dump(mode="json") for item in config.ethernet_segments]
    network.gateway_routes = [item.model_dump(mode="json") for item in config.gateway_routes]
    command = GatewayRouteCommand(
        command_id="route-command-001",
        expected_version=1,
        route_id="can-to-lin",
        payload=[10, 20],
        advance_time_us=50,
    )
    session = FakeSession([network, None])
    execution, updated, duplicate = await execute_gateway_route(
        cast(AsyncSession, session),
        vehicle=vehicle,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert not duplicate
    assert execution.result["bit_count"] == 63
    assert execution.result["duration_us"] == 3150
    assert execution.result["started_at_us"] == 150
    assert execution.result["completed_at_us"] == 3300
    assert execution.result["sequence"] == 7
    assert updated.next_sequence == 8
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.vehicle.gateway.routed.v1"
    assert "payload" not in event.payload


@pytest.mark.asyncio
async def test_ethernet_route_rounds_duration_up_and_replay_is_exact() -> None:
    vehicle, network, gateway, producer, consumer = context()
    config = configuration(gateway, producer, consumer)
    network.lin_channels = [item.model_dump(mode="json") for item in config.lin_channels]
    network.ethernet_segments = [item.model_dump(mode="json") for item in config.ethernet_segments]
    network.gateway_routes = [item.model_dump(mode="json") for item in config.gateway_routes]
    command = GatewayRouteCommand(
        command_id="route-command-002",
        expected_version=1,
        route_id="lin-to-ethernet",
        payload=[10, 20],
    )
    fresh = FakeSession([network, None])
    routed, _, _ = await execute_gateway_route(
        cast(AsyncSession, fresh),
        vehicle=vehicle,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert routed.result["bit_count"] == 320
    assert routed.result["duration_us"] == 4
    network.version = 1
    network.simulation_time_us = 100
    network.next_sequence = 7
    existing = MultiBusGatewayExecution(
        id=uuid4(),
        network_id=network.id,
        command_id=command.command_id,
        operation="route",
        route_id=command.route_id,
        request=command.model_dump(mode="json"),
        result={"duration_us": 4},
        previous_version=1,
        network_version=2,
        requested_by_user_id=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert (
        await execute_gateway_route(
            cast(AsyncSession, FakeSession([network, existing])),
            vehicle=vehicle,
            command=command,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    )[2]
    changed = command.model_copy(update={"payload": [11, 20]})
    with pytest.raises(MultiBusGatewayCommandConflictError):
        await execute_gateway_route(
            cast(AsyncSession, FakeSession([network, existing])),
            vehicle=vehicle,
            command=changed,
            actor_user_id=uuid4(),
            correlation_id=None,
        )


def test_campaign_contract_is_bounded_and_requires_unique_steps() -> None:
    data = campaign().model_dump(mode="json")
    data["steps"][1]["identifier"] = data["steps"][0]["identifier"]
    with pytest.raises(ValidationError, match="unique"):
        MultiBusCampaignCommand.model_validate(data)
    data = campaign().model_dump(mode="json")
    data["steps"] = data["steps"] * 33
    with pytest.raises(ValidationError):
        MultiBusCampaignCommand.model_validate(data)


@pytest.mark.asyncio
async def test_campaign_produces_deterministic_trace_and_performance_metrics() -> None:
    vehicle, network, _, _, _ = configured_context()
    session = FakeSession([network, None])
    execution, updated, duplicate = await execute_multibus_campaign(
        cast(AsyncSession, session),
        vehicle=vehicle,
        command=campaign(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert not duplicate
    assert execution.status == "performance_degraded"
    assert execution.result["step_count"] == 2
    assert execution.result["delivered_count"] == 2
    assert execution.result["budget_violation_count"] == 1
    assert execution.result["occupied_us"] == 3154
    assert execution.result["idle_us"] == 75
    assert execution.result["window_us"] == 3229
    assert execution.result["maximum_latency_us"] == 3150
    assert execution.result["p95_latency_us"] == 3150
    assert execution.result["protocol_counts"] == {"can": 0, "lin": 1, "ethernet": 1}
    assert [item["sequence"] for item in execution.result["traces"]] == [7, 8]
    assert updated.simulation_time_us == 3329
    assert updated.next_sequence == 9
    assert updated.version == 2
    assert all("payload" not in trace for trace in execution.result["traces"])
    assert all("payload" not in step for step in execution.request_summary["steps"])
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.event_type == "atep.vehicle.multibus.campaign.completed.v1"
    assert "traces" not in event.payload
    assert audit.action == "vehicle.multibus_campaign_completed"


@pytest.mark.asyncio
async def test_campaign_integrates_loss_and_gateway_unavailable_scenarios() -> None:
    vehicle, network, _, _, _ = configured_context()
    command = campaign().model_copy(
        update={
            "steps": [
                campaign().steps[0].model_copy(update={"fault": MultiBusCampaignFault.FRAME_LOSS}),
                campaign()
                .steps[1]
                .model_copy(update={"fault": MultiBusCampaignFault.GATEWAY_UNAVAILABLE}),
            ]
        }
    )
    execution, updated, _ = await execute_multibus_campaign(
        cast(AsyncSession, FakeSession([network, None])),
        vehicle=vehicle,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert execution.status == "failed"
    assert execution.result["failed_count"] == 2
    assert execution.result["delivered_count"] == 0
    assert execution.result["occupied_us"] == 3150
    assert execution.result["traces"][0]["failure_reason"] == "frame_loss"
    assert execution.result["traces"][1]["sequence"] is None
    assert execution.result["traces"][1]["duration_us"] == 0
    assert updated.next_sequence == 8


@pytest.mark.asyncio
async def test_campaign_exact_replay_is_mutation_free_and_changed_reuse_conflicts() -> None:
    vehicle, network, _, _, _ = configured_context()
    command = campaign()
    existing, _, _ = await execute_multibus_campaign(
        cast(AsyncSession, FakeSession([network, None])),
        vehicle=vehicle,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    time_after_first = network.simulation_time_us
    sequence_after_first = network.next_sequence
    assert (
        await execute_multibus_campaign(
            cast(AsyncSession, FakeSession([network, existing])),
            vehicle=vehicle,
            command=command,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    )[2]
    assert network.simulation_time_us == time_after_first
    assert network.next_sequence == sequence_after_first
    changed = command.model_copy(update={"steps": [command.steps[0]]})
    with pytest.raises(MultiBusCampaignCommandConflictError):
        await execute_multibus_campaign(
            cast(AsyncSession, FakeSession([network, existing])),
            vehicle=vehicle,
            command=changed,
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_campaign_prevalidation_rejects_unknown_route_without_mutation() -> None:
    vehicle, network, _, _, _ = configured_context()
    command = campaign().model_copy(
        update={
            "steps": [campaign().steps[0].model_copy(update={"route_id": "unknown-route"})]
        }
    )
    with pytest.raises(MultiBusCampaignContractError) as error:
        await execute_multibus_campaign(
            cast(AsyncSession, FakeSession([network, None])),
            vehicle=vehicle,
            command=command,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details == {
        "reason": "step battery-to-lin references an invalid gateway route"
    }
    assert network.version == 1
    assert network.simulation_time_us == 100
    assert network.next_sequence == 7
