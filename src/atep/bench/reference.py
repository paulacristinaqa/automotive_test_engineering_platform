"""Reference powertrain network and cyclic schedule for the virtual bench demo."""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from atep.bench.vector_dbc import DbcNode, VectorNetworkSpec
from atep.bench.vector_trace import TraceFrame
from atep.can_network.dbc_service import encode_message
from atep.can_network.schemas import CanDbcMessage, CanFrameContract

BMS_ID = UUID("00000000-0000-4000-8000-0000000000b1")
VCU_ID = UUID("00000000-0000-4000-8000-0000000000c1")


@dataclass(frozen=True)
class ScheduledFrame:
    frame: TraceFrame
    contract_id: str
    values: dict[str, Decimal]


@dataclass(frozen=True)
class CyclicMessage:
    contract_id: str
    period_ms: int
    offset_us: int


CYCLIC_MESSAGES = (
    CyclicMessage("bms-status", period_ms=10, offset_us=0),
    CyclicMessage("vcu-command", period_ms=20, offset_us=1_000),
    CyclicMessage("bms-cells", period_ms=100, offset_us=2_000),
)


def _signal(
    name: str,
    start: int,
    length: int,
    *,
    order: str = "intel",
    signed: bool = False,
    factor: str = "1",
    offset: str = "0",
    minimum: str | None = None,
    maximum: str | None = None,
    unit: str = "",
) -> dict[str, object]:
    return {
        "identifier": name,
        "start_bit": start,
        "bit_length": length,
        "byte_order": order,
        "signed": signed,
        "factor": factor,
        "offset": offset,
        "minimum": minimum,
        "maximum": maximum,
        "unit": unit,
    }


def reference_spec() -> VectorNetworkSpec:
    """A small CAN FD powertrain network: BMS and VCU, three cyclic messages."""
    frames = [
        CanFrameContract.model_validate(item)
        for item in (
            {
                "identifier": "bms-status",
                "frame_id": 0x180,
                "dlc": 4,
                "producer_node_id": str(BMS_ID),
                "consumer_node_ids": [str(VCU_ID)],
            },
            {
                "identifier": "vcu-command",
                "frame_id": 0x18FF5010,
                "frame_format": "extended",
                "dlc": 8,
                "producer_node_id": str(VCU_ID),
                "consumer_node_ids": [str(BMS_ID)],
            },
            {
                "identifier": "bms-cells",
                "frame_id": 0x200,
                "protocol": "fd",
                "dlc": 16,
                "bitrate_switch": True,
                "producer_node_id": str(BMS_ID),
                "consumer_node_ids": [str(VCU_ID)],
            },
        )
    ]
    messages = [
        CanDbcMessage.model_validate(
            {
                "contract_id": "bms-status",
                "signals": [
                    _signal(
                        "PackVoltage", 0, 12, factor="0.1", minimum="0", maximum="409.5", unit="V"
                    ),
                    _signal(
                        "PackCurrent",
                        23,
                        12,
                        order="motorola",
                        signed=True,
                        factor="0.5",
                        offset="-100",
                        unit="A",
                    ),
                ],
            }
        ),
        CanDbcMessage.model_validate(
            {
                "contract_id": "vcu-command",
                "signals": [
                    _signal("TorqueRequest", 0, 16, signed=True, factor="0.1", unit="Nm"),
                    _signal("ContactorClose", 16, 1),
                    _signal("AliveCounter", 56, 4),
                ],
            }
        ),
        CanDbcMessage.model_validate(
            {
                "contract_id": "bms-cells",
                "signals": [
                    _signal(f"CellVoltage{index + 1}", index * 16, 16, factor="0.001", unit="V")
                    for index in range(4)
                ]
                + [_signal("MaxCellTemp", 64, 8, offset="-40", unit="degC")],
            }
        ),
    ]
    return VectorNetworkSpec(
        network_identifier="bench-powertrain-can",
        display_name="Virtual bench powertrain CAN",
        revision="XI-1",
        bitrate_kbps=500,
        can_fd_enabled=True,
        data_bitrate_kbps=2000,
        nodes=[DbcNode(BMS_ID, "BMS"), DbcNode(VCU_ID, "VCU")],
        frames=frames,
        messages={message.contract_id: message for message in messages},
    )


def _values(contract_id: str, cycle: int) -> dict[str, Decimal]:
    if contract_id == "bms-status":
        return {
            "PackVoltage": Decimal("350.0") + Decimal(cycle % 50) * Decimal("0.1"),
            "PackCurrent": Decimal(-20) + Decimal(cycle % 40) * Decimal("0.5"),
        }
    if contract_id == "vcu-command":
        return {
            "TorqueRequest": Decimal(-10) + Decimal(cycle % 100) * Decimal("0.5"),
            "ContactorClose": Decimal(1),
            "AliveCounter": Decimal(cycle % 16),
        }
    cells = {
        f"CellVoltage{index + 1}": Decimal("3.700")
        + Decimal((cycle + index) % 20) * Decimal("0.001")
        for index in range(4)
    }
    return cells | {"MaxCellTemp": Decimal(25 + cycle % 5)}


def build_schedule(spec: VectorNetworkSpec, *, duration_ms: int) -> list[ScheduledFrame]:
    """Encode every cyclic message for `duration_ms` with the ATEP DBC codec."""
    if not 1 <= duration_ms <= 60_000:
        raise ValueError("duration must be between 1 ms and 60 s")
    contracts = {frame.identifier: frame for frame in spec.frames}
    schedule: list[ScheduledFrame] = []
    for cyclic in CYCLIC_MESSAGES:
        contract = contracts[cyclic.contract_id]
        message = spec.messages[cyclic.contract_id]
        for cycle in range(0, duration_ms // cyclic.period_ms):
            values = _values(cyclic.contract_id, cycle)
            payload, _, _ = encode_message(message, dlc=contract.dlc, values=values)
            frame = TraceFrame(
                timestamp_us=cycle * cyclic.period_ms * 1_000 + cyclic.offset_us,
                arbitration_id=contract.frame_id,
                is_extended_id=contract.frame_format.value == "extended",
                data=bytes(payload),
                is_fd=contract.protocol.value == "fd",
                bitrate_switch=contract.bitrate_switch,
            )
            schedule.append(ScheduledFrame(frame, cyclic.contract_id, values))
    return sorted(schedule, key=lambda item: item.frame.timestamp_us)
