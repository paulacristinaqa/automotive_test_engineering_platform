from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.can_network.dbc_service import (
    create_dbc_catalogue,
    dbc_bit_positions,
    decode_message,
    decode_signals,
    encode_message,
    encode_signals,
)
from atep.can_network.models import CanDbcCatalogue, CanNetwork, CanSignalCodecExecution
from atep.can_network.schemas import (
    CanDbcCatalogueCreate,
    CanDbcMessage,
    CanDbcSignal,
    CanSignalDecodeCommand,
    CanSignalEncodeCommand,
)
from atep.core.errors import (
    CanDbcCatalogueAlreadyExistsError,
    CanNetworkContractError,
    CanNetworkVersionConflictError,
    CanSignalCodecCommandConflictError,
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
        now = datetime.now(UTC)
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()
            if getattr(value, "created_at", None) is None:
                value.created_at = now
            if getattr(value, "updated_at", None) is None:
                value.updated_at = now


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


def _network(target: Vehicle, producer: UUID) -> CanNetwork:
    now = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
    return CanNetwork(
        id=uuid4(),
        vehicle_id=target.id,
        identifier="powertrain-can",
        display_name="Powertrain CAN",
        bitrate_kbps=500,
        nodes=[{"ecu_id": str(producer), "role": "participant"}],
        frame_contracts=[
            {
                "identifier": "bms-status",
                "frame_id": 0x180,
                "frame_format": "standard",
                "dlc": 4,
                "producer_node_id": str(producer),
                "consumer_node_ids": [],
            }
        ],
        version=4,
        simulation_time_us=0,
        next_sequence=1,
        created_at=now,
        updated_at=now,
    )


def _message() -> CanDbcMessage:
    return CanDbcMessage(
        contract_id="bms-status",
        signals=[
            {
                "identifier": "PackVoltage",
                "start_bit": 0,
                "bit_length": 12,
                "byte_order": "intel",
                "factor": "0.1",
                "offset": "0",
                "minimum": "0",
                "maximum": "409.5",
                "unit": "V",
            },
            {
                "identifier": "PackCurrent",
                "start_bit": 23,
                "bit_length": 12,
                "byte_order": "motorola",
                "signed": True,
                "factor": "0.5",
                "offset": "-100",
                "unit": "A",
            },
        ],
    )


def _catalogue(network: CanNetwork) -> CanDbcCatalogue:
    now = datetime.now(UTC)
    return CanDbcCatalogue(
        id=uuid4(),
        network_id=network.id,
        identifier="reference-dbc",
        display_name="Reference DBC",
        revision="1.0.0",
        messages=[_message().model_dump(mode="json")],
        network_version=5,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )


def _create_command() -> CanDbcCatalogueCreate:
    return CanDbcCatalogueCreate(
        expected_version=4,
        identifier="reference-dbc",
        display_name="Reference DBC",
        revision="1.0.0",
        messages=[_message()],
    )


def test_dbc_schema_rejects_duplicate_signals_and_invalid_range() -> None:
    signal = {
        "identifier": "Voltage",
        "start_bit": 0,
        "bit_length": 8,
        "byte_order": "intel",
    }
    with pytest.raises(ValidationError, match="must be unique"):
        CanDbcMessage(contract_id="bms-status", signals=[signal, signal])
    with pytest.raises(ValidationError, match="minimum"):
        CanDbcSignal(**signal, minimum="10", maximum="5")
    with pytest.raises(ValidationError):
        CanDbcSignal(**signal, factor="0")


def test_intel_and_motorola_bit_positions_follow_dbc_semantics() -> None:
    intel = CanDbcSignal(
        identifier="Intel", start_bit=0, bit_length=12, byte_order="intel"
    )
    motorola = CanDbcSignal(
        identifier="Motorola", start_bit=7, bit_length=12, byte_order="motorola"
    )
    assert dbc_bit_positions(intel) == list(range(12))
    assert dbc_bit_positions(motorola) == [7, 6, 5, 4, 3, 2, 1, 0, 15, 14, 13, 12]


def test_codec_round_trip_covers_scaling_offset_signedness_and_byte_order() -> None:
    message = _message()
    payload, raw_values, physical_values = encode_message(
        message,
        dlc=4,
        values={"PackVoltage": Decimal("300.0"), "PackCurrent": Decimal("-125.0")},
    )
    assert raw_values == {"PackVoltage": 3000, "PackCurrent": -50}
    assert payload == [0xB8, 0x0B, 0xFC, 0xE0]
    decoded_raw, decoded_physical = decode_message(message, payload=payload)
    assert decoded_raw == raw_values
    assert decoded_physical == physical_values


def test_codec_rejects_nonrepresentable_missing_and_out_of_range_values() -> None:
    message = _message()
    with pytest.raises(CanNetworkContractError) as nonrepresentable:
        encode_message(
            message,
            dlc=4,
            values={"PackVoltage": Decimal("300.05"), "PackCurrent": Decimal("-125")},
        )
    assert "representable" in cast(dict[str, Any], nonrepresentable.value.details)["reason"]
    with pytest.raises(CanNetworkContractError) as missing:
        encode_message(message, dlc=4, values={"PackVoltage": Decimal("300")})
    assert "exactly match" in cast(dict[str, Any], missing.value.details)["reason"]
    with pytest.raises(CanNetworkContractError) as out_of_range:
        encode_message(
            message,
            dlc=4,
            values={"PackVoltage": Decimal("500"), "PackCurrent": Decimal("-125")},
        )
    assert "maximum" in cast(dict[str, Any], out_of_range.value.details)["reason"]


@pytest.mark.asyncio
async def test_catalogue_creation_validates_layout_versions_and_evidence() -> None:
    target = _vehicle()
    network = _network(target, uuid4())
    session = FakeSession([network, None])
    catalogue, updated = await create_dbc_catalogue(
        cast(AsyncSession, session),
        vehicle=target,
        command=_create_command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert catalogue.network_version == 5
    assert updated.version == 5
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.event_type == "atep.can.dbc.catalogue.created.v1"
    assert event.payload["signal_count"] == 2
    assert "messages" not in event.payload
    assert "messages" not in audit.details

    with pytest.raises(CanDbcCatalogueAlreadyExistsError):
        await create_dbc_catalogue(
            cast(AsyncSession, FakeSession([network, catalogue])),
            vehicle=target,
            command=_create_command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    with pytest.raises(CanNetworkVersionConflictError):
        await create_dbc_catalogue(
            cast(AsyncSession, FakeSession([network, None])),
            vehicle=target,
            command=_create_command().model_copy(update={"expected_version": 3}),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_catalogue_creation_rejects_overlap_and_dlc_overflow() -> None:
    target = _vehicle()
    network = _network(target, uuid4())
    overlapping = _create_command().model_copy(
        update={
            "messages": [
                CanDbcMessage(
                    contract_id="bms-status",
                    signals=[
                        {
                            "identifier": "First",
                            "start_bit": 0,
                            "bit_length": 8,
                            "byte_order": "intel",
                        },
                        {
                            "identifier": "Second",
                            "start_bit": 7,
                            "bit_length": 8,
                            "byte_order": "intel",
                        },
                    ],
                )
            ]
        }
    )
    with pytest.raises(CanNetworkContractError) as overlap:
        await create_dbc_catalogue(
            cast(AsyncSession, FakeSession([network, None])),
            vehicle=target,
            command=overlapping,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert "overlap" in cast(dict[str, Any], overlap.value.details)["reason"]

    overflowing = _create_command().model_copy(
        update={
            "messages": [
                CanDbcMessage(
                    contract_id="bms-status",
                    signals=[
                        {
                            "identifier": "Overflow",
                            "start_bit": 31,
                            "bit_length": 2,
                            "byte_order": "intel",
                        }
                    ],
                )
            ]
        }
    )
    with pytest.raises(CanNetworkContractError) as overflow:
        await create_dbc_catalogue(
            cast(AsyncSession, FakeSession([network, None])),
            vehicle=target,
            command=overflowing,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert "DLC" in cast(dict[str, Any], overflow.value.details)["reason"]


@pytest.mark.asyncio
async def test_encode_execution_is_replay_safe_and_payload_free_in_observability() -> None:
    target = _vehicle()
    network = _network(target, uuid4())
    catalogue = _catalogue(network)
    command = CanSignalEncodeCommand(
        command_id="codec-command-001",
        contract_id="bms-status",
        values={"PackVoltage": "300", "PackCurrent": "-125"},
    )
    session = FakeSession([network, None, catalogue])
    execution, _, duplicate = await encode_signals(
        cast(AsyncSession, session),
        vehicle=target,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert not duplicate
    assert execution.result["payload"] == [0xB8, 0x0B, 0xFC, 0xE0]
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert "payload" not in event.payload
    assert "physical_values" not in event.payload
    assert "payload" not in audit.details

    replay = await encode_signals(
        cast(AsyncSession, FakeSession([network, execution])),
        vehicle=target,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert replay[2]
    with pytest.raises(CanSignalCodecCommandConflictError):
        await encode_signals(
            cast(AsyncSession, FakeSession([network, execution])),
            vehicle=target,
            command=command.model_copy(
                update={
                    "values": {
                        "PackVoltage": Decimal("301"),
                        "PackCurrent": Decimal("-125"),
                    }
                }
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_decode_execution_validates_dlc_and_persists_physical_values() -> None:
    target = _vehicle()
    network = _network(target, uuid4())
    catalogue = _catalogue(network)
    command = CanSignalDecodeCommand(
        command_id="decode-command-001",
        contract_id="bms-status",
        payload=[0xB8, 0x0B, 0xFC, 0xE0],
    )
    execution, _, duplicate = await decode_signals(
        cast(AsyncSession, FakeSession([network, None, catalogue])),
        vehicle=target,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert not duplicate
    assert execution.operation == "decode"
    assert execution.result["raw_values"] == {"PackVoltage": 3000, "PackCurrent": -50}
    assert execution.result["physical_values"] == {
        "PackVoltage": "300.0",
        "PackCurrent": "-125.0",
    }
    with pytest.raises(CanNetworkContractError) as invalid_dlc:
        await decode_signals(
            cast(AsyncSession, FakeSession([network, None, catalogue])),
            vehicle=target,
            command=command.model_copy(update={"payload": [0]}),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert "DLC" in cast(dict[str, Any], invalid_dlc.value.details)["reason"]


def test_dbc_models_preserve_catalogue_and_codec_evidence() -> None:
    assert {"messages", "revision", "network_version"} <= set(
        CanDbcCatalogue.__table__.columns.keys()
    )
    assert {"operation", "request", "result", "contract_id"} <= set(
        CanSignalCodecExecution.__table__.columns.keys()
    )
