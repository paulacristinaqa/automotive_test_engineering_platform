from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CanFrameFormat(StrEnum):
    STANDARD = "standard"
    EXTENDED = "extended"


class CanFrameProtocol(StrEnum):
    CLASSIC = "classic"
    FD = "fd"


CAN_FD_PAYLOAD_LENGTHS = frozenset({0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64})


class CanNodeRole(StrEnum):
    PARTICIPANT = "participant"
    GATEWAY = "gateway"
    MONITOR = "monitor"


class CanNodeErrorMode(StrEnum):
    ERROR_ACTIVE = "error_active"
    ERROR_PASSIVE = "error_passive"
    BUS_OFF = "bus_off"


class CanFaultType(StrEnum):
    TRANSMISSION_ERROR = "transmission_error"
    RECEPTION_ERROR = "reception_error"
    FRAME_LOSS = "frame_loss"


class CanNodeErrorState(BaseModel):
    transmit_error_count: int = Field(ge=0, le=256)
    receive_error_count: int = Field(ge=0, le=255)
    state: CanNodeErrorMode


class CanNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ecu_id: UUID
    role: CanNodeRole = CanNodeRole.PARTICIPANT


class CanFrameContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_-]+$")
    frame_id: int = Field(ge=0, le=0x1FFFFFFF)
    frame_format: CanFrameFormat = CanFrameFormat.STANDARD
    protocol: CanFrameProtocol = CanFrameProtocol.CLASSIC
    dlc: int = Field(ge=0, le=64)
    bitrate_switch: bool = False
    producer_node_id: UUID
    consumer_node_ids: list[UUID] = Field(default_factory=list, max_length=63)

    @model_validator(mode="after")
    def validate_contract(self) -> "CanFrameContract":
        if self.frame_format is CanFrameFormat.STANDARD and self.frame_id > 0x7FF:
            raise ValueError("standard CAN frame_id must be at most 0x7FF")
        if self.protocol is CanFrameProtocol.CLASSIC and self.dlc > 8:
            raise ValueError("classic CAN frame DLC must be at most 8")
        if self.protocol is CanFrameProtocol.CLASSIC and self.bitrate_switch:
            raise ValueError("bitrate switching is available only for CAN FD frames")
        if self.protocol is CanFrameProtocol.FD and self.dlc not in CAN_FD_PAYLOAD_LENGTHS:
            raise ValueError("CAN FD payload length must use an ISO-defined DLC size")
        if self.producer_node_id in self.consumer_node_ids:
            raise ValueError("producer cannot also be a consumer")
        if len(set(self.consumer_node_ids)) != len(self.consumer_node_ids):
            raise ValueError("consumer node identifiers must be unique")
        return self


class CanNetworkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_-]+$")
    display_name: str = Field(min_length=2, max_length=120)
    bitrate_kbps: int = Field(default=500, ge=10, le=1000)
    can_fd_enabled: bool = False
    data_bitrate_kbps: int | None = Field(default=None, ge=10, le=8000)
    nodes: list[CanNode] = Field(min_length=1, max_length=64)
    frame_contracts: list[CanFrameContract] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def validate_topology(self) -> "CanNetworkCreate":
        if self.can_fd_enabled:
            if self.data_bitrate_kbps is None:
                raise ValueError("CAN FD networks require a data bitrate")
            if self.data_bitrate_kbps < self.bitrate_kbps:
                raise ValueError("CAN FD data bitrate must be at least the nominal bitrate")
        elif self.data_bitrate_kbps is not None:
            raise ValueError("classic CAN networks cannot define a data bitrate")
        node_ids = [item.ecu_id for item in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("CAN node ECU identifiers must be unique")
        contract_ids = [item.identifier for item in self.frame_contracts]
        if len(set(contract_ids)) != len(contract_ids):
            raise ValueError("CAN frame contract identifiers must be unique")
        frame_keys = [(item.frame_format, item.frame_id) for item in self.frame_contracts]
        if len(set(frame_keys)) != len(frame_keys):
            raise ValueError("CAN frame identifiers must be unique per format")
        known = set(node_ids)
        for contract in self.frame_contracts:
            if contract.protocol is CanFrameProtocol.FD and not self.can_fd_enabled:
                raise ValueError("CAN FD frame contracts require a CAN FD-enabled network")
            if (
                contract.producer_node_id not in known
                or not set(contract.consumer_node_ids) <= known
            ):
                raise ValueError("CAN frame contracts may reference only declared nodes")
        return self


class CanFrameSubmitCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$")
    expected_version: int = Field(ge=1)
    contract_id: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_-]+$")
    producer_node_id: UUID
    payload: list[int] = Field(max_length=64)
    advance_time_us: int = Field(default=0, ge=0, le=10_000_000)

    @field_validator("payload")
    @classmethod
    def validate_payload_bytes(cls, value: list[int]) -> list[int]:
        if any(item < 0 or item > 255 for item in value):
            raise ValueError("CAN payload bytes must be between 0 and 255")
        return value


class CanNetworkResponse(BaseModel):
    id: UUID
    vehicle_id: str
    identifier: str
    display_name: str
    bitrate_kbps: int
    can_fd_enabled: bool
    data_bitrate_kbps: int | None
    nodes: list[CanNode]
    frame_contracts: list[CanFrameContract]
    error_states: dict[str, CanNodeErrorState]
    version: int
    simulation_time_us: int
    next_sequence: int
    created_at: datetime
    updated_at: datetime


class CanFrameTransmissionResponse(BaseModel):
    command_id: str
    vehicle_id: str
    network_id: str
    contract_id: str
    producer_node_id: UUID
    frame_id: int
    frame_format: CanFrameFormat
    protocol: CanFrameProtocol
    bitrate_switch: bool
    payload: list[int]
    sequence: int
    transmission_time_us: int
    previous_version: int
    network_version: int
    duplicate: bool
    created_at: datetime


class CanFrameTransmissionPage(BaseModel):
    items: list[CanFrameTransmissionResponse]
    total: int
    limit: int
    offset: int


class CanFaultInjectionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$")
    expected_version: int = Field(ge=1)
    contract_id: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_-]+$")
    target_node_id: UUID
    fault_type: CanFaultType
    occurrences: int = Field(default=1, ge=1, le=32)
    advance_time_us: int = Field(default=0, ge=0, le=10_000_000)


class CanBusRecoveryCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$")
    expected_version: int = Field(ge=1)
    target_node_id: UUID
    recessive_sequences: int = Field(default=128, ge=128, le=1024)


class CanFaultExecutionResponse(BaseModel):
    command_id: str
    vehicle_id: str
    network_id: str
    operation: str
    target_node_id: UUID
    result: dict[str, object]
    previous_version: int
    network_version: int
    duplicate: bool
    created_at: datetime


class CanFaultExecutionPage(BaseModel):
    items: list[CanFaultExecutionResponse]
    total: int
    limit: int
    offset: int


class CanArbitrationContender(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_id: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_-]+$")
    producer_node_id: UUID
    payload: list[int] = Field(max_length=64)
    ready_offset_us: int = Field(default=0, ge=0, le=10_000_000)

    @field_validator("payload")
    @classmethod
    def validate_payload_bytes(cls, value: list[int]) -> list[int]:
        if any(item < 0 or item > 255 for item in value):
            raise ValueError("CAN payload bytes must be between 0 and 255")
        return value


class CanArbitrationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=8, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$")
    expected_version: int = Field(ge=1)
    contenders: list[CanArbitrationContender] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_contenders(self) -> "CanArbitrationCommand":
        contracts = [item.contract_id for item in self.contenders]
        if len(set(contracts)) != len(contracts):
            raise ValueError("arbitration contender contracts must be unique")
        return self


class CanDeliveryEvidence(BaseModel):
    consumer_node_id: UUID
    received_at_us: int
    latency_us: int


class CanArbitratedFrame(BaseModel):
    rank: int
    sequence: int
    contract_id: str
    frame_id: int
    frame_format: CanFrameFormat
    protocol: CanFrameProtocol = CanFrameProtocol.CLASSIC
    bitrate_switch: bool = False
    producer_node_id: UUID
    dlc: int
    bit_count: int
    nominal_bit_count: int = 0
    data_bit_count: int = 0
    nominal_phase_duration_us: int = 0
    data_phase_duration_us: int = 0
    ready_at_us: int
    started_at_us: int
    completed_at_us: int
    duration_us: int
    deliveries: list[CanDeliveryEvidence] = Field(max_length=63)


class CanBusUtilization(BaseModel):
    window_start_us: int
    window_end_us: int
    window_duration_us: int
    occupied_us: int
    idle_us: int
    utilization_percent: float = Field(ge=0, le=100)
    maximum_latency_us: int


class CanArbitrationResponse(BaseModel):
    command_id: str
    vehicle_id: str
    network_id: str
    previous_version: int
    network_version: int
    frames: list[CanArbitratedFrame] = Field(max_length=64)
    utilization: CanBusUtilization
    duplicate: bool
    created_at: datetime


class CanArbitrationPage(BaseModel):
    items: list[CanArbitrationResponse]
    total: int
    limit: int
    offset: int


class CanDbcByteOrder(StrEnum):
    INTEL = "intel"
    MOTOROLA = "motorola"


class CanDbcSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    start_bit: int = Field(ge=0, le=511)
    bit_length: int = Field(ge=1, le=512)
    byte_order: CanDbcByteOrder
    signed: bool = False
    factor: Decimal = Field(default=Decimal("1"), gt=0)
    offset: Decimal = Decimal("0")
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    unit: str = Field(default="", max_length=32)

    @model_validator(mode="after")
    def validate_physical_range(self) -> "CanDbcSignal":
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("signal minimum must be less than or equal to maximum")
        return self


class CanDbcMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_id: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_-]+$")
    signals: list[CanDbcSignal] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_unique_signals(self) -> "CanDbcMessage":
        identifiers = [signal.identifier for signal in self.signals]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("DBC signal identifiers must be unique per message")
        return self


class CanDbcCatalogueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    identifier: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_-]+$")
    display_name: str = Field(min_length=2, max_length=120)
    revision: str = Field(min_length=1, max_length=40)
    messages: list[CanDbcMessage] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_unique_messages(self) -> "CanDbcCatalogueCreate":
        contracts = [message.contract_id for message in self.messages]
        if len(set(contracts)) != len(contracts):
            raise ValueError("DBC messages must reference unique frame contracts")
        return self


class CanDbcCatalogueResponse(BaseModel):
    id: UUID
    vehicle_id: str
    network_id: str
    identifier: str
    display_name: str
    revision: str
    messages: list[CanDbcMessage]
    network_version: int
    created_at: datetime
    updated_at: datetime


class CanSignalEncodeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$")
    contract_id: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_-]+$")
    values: dict[str, Decimal] = Field(min_length=1, max_length=64)


class CanSignalDecodeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$")
    contract_id: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_-]+$")
    payload: list[int] = Field(max_length=64)

    @field_validator("payload")
    @classmethod
    def validate_payload_bytes(cls, value: list[int]) -> list[int]:
        if any(item < 0 or item > 255 for item in value):
            raise ValueError("CAN payload bytes must be between 0 and 255")
        return value


class CanSignalCodecResponse(BaseModel):
    command_id: str
    vehicle_id: str
    network_id: str
    operation: str
    contract_id: str
    payload: list[int]
    raw_values: dict[str, int]
    physical_values: dict[str, Decimal]
    duplicate: bool
    created_at: datetime


class CanSignalCodecPage(BaseModel):
    items: list[CanSignalCodecResponse]
    total: int
    limit: int
    offset: int
