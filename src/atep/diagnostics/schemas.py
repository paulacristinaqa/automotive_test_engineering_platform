import re
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

CommandId = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
]
DtcCode = Annotated[str, StringConstraints(pattern=r"^[0-9A-F]{6}$")]
DidValue = bool | int | float | str
RoutineParameters = dict[str, DidValue]


class UdsServiceId(IntEnum):
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    ECU_RESET = 0x11
    CLEAR_DIAGNOSTIC_INFORMATION = 0x14
    READ_DTC_INFORMATION = 0x19
    READ_DATA_BY_IDENTIFIER = 0x22
    WRITE_DATA_BY_IDENTIFIER = 0x2E
    SECURITY_ACCESS = 0x27
    ROUTINE_CONTROL = 0x31
    REQUEST_DOWNLOAD = 0x34
    TRANSFER_DATA = 0x36
    REQUEST_TRANSFER_EXIT = 0x37


class UdsNegativeResponseCode(IntEnum):
    INCORRECT_MESSAGE_LENGTH_OR_INVALID_FORMAT = 0x13
    WRONG_BLOCK_SEQUENCE_COUNTER = 0x73
    REQUEST_SEQUENCE_ERROR = 0x24
    CONDITIONS_NOT_CORRECT = 0x22
    REQUEST_OUT_OF_RANGE = 0x31
    SECURITY_ACCESS_DENIED = 0x33
    INVALID_KEY = 0x35
    EXCEED_NUMBER_OF_ATTEMPTS = 0x36
    REQUIRED_TIME_DELAY_NOT_EXPIRED = 0x37
    SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION = 0x7F


class DiagnosticSessionType(StrEnum):
    DEFAULT = "default"
    PROGRAMMING = "programming"
    EXTENDED = "extended"


class DtcSeverity(StrEnum):
    INFORMATION = "information"
    WARNING = "warning"
    CRITICAL = "critical"


class DidDataType(StrEnum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    STRING = "string"


class RoutineControlType(IntEnum):
    START = 0x01
    STOP = 0x02
    REQUEST_RESULTS = 0x03


class RoutineStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"


class SecurityAccessType(IntEnum):
    REQUEST_SEED_LEVEL_1 = 0x01
    SEND_KEY_LEVEL_1 = 0x02


class UdsEcuResetType(IntEnum):
    HARD_RESET = 0x01
    KEY_OFF_ON_RESET = 0x02
    SOFT_RESET = 0x03


class DiagnosticEcuResetCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: CommandId
    reset_type: UdsEcuResetType
    expected_ecu_version: int = Field(ge=1)
    expected_session_version: int = Field(ge=1)
    expected_security_version: int = Field(ge=1)


class FlashRequestDownloadCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: CommandId
    memory_address: int = Field(ge=0, le=0xFFFF)
    memory_size: int = Field(ge=1, le=65_536)
    firmware_version: str = Field(min_length=1, max_length=20, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    data_format_identifier: int = Field(default=0, ge=0, le=0)
    expected_ecu_version: int = Field(ge=1)
    expected_session_version: int = Field(ge=1)
    expected_security_version: int = Field(ge=1)

    @model_validator(mode="after")
    def bounded_address_range(self) -> "FlashRequestDownloadCommand":
        if self.memory_address + self.memory_size > 65_536:
            raise ValueError("download range exceeds the 16-bit ECU address space")
        return self


class FlashTransferDataCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    command_id: CommandId
    block_sequence_counter: int = Field(ge=0, le=255)
    data_hex: SecretStr = Field(min_length=2, max_length=512)
    expected_transfer_version: int = Field(ge=1)

    @field_validator("data_hex")
    @classmethod
    def hexadecimal_block(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw) % 2 != 0 or re.fullmatch(r"[0-9A-Fa-f]+", raw) is None:
            raise ValueError("data_hex must contain an even number of hexadecimal characters")
        return SecretStr(raw.upper())


class FlashTransferExitCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: CommandId
    expected_transfer_version: int = Field(ge=1)
    expected_ecu_version: int = Field(ge=1)
    expected_sha256: str = Field(pattern=r"^[0-9A-Fa-f]{64}$")

    @field_validator("expected_sha256")
    @classmethod
    def normalized_digest(cls, value: str) -> str:
        return value.lower()


class FlashStateResponse(BaseModel):
    ecu_id: str
    status: str
    memory_address: int
    memory_size: int
    firmware_version: str
    max_block_length: int
    next_block_sequence_counter: int
    bytes_received: int
    image_sha256: str | None
    transfer_version: int


class SecurityAccessCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    command_id: CommandId
    access_type: SecurityAccessType
    expected_session_version: int = Field(ge=1)
    expected_security_version: int = Field(ge=1)
    key: SecretStr | None = Field(default=None, min_length=16, max_length=16)

    @field_validator("key")
    @classmethod
    def hexadecimal_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value()
        if re.fullmatch(r"[0-9A-Fa-f]{16}", raw) is None:
            raise ValueError("key must contain exactly 16 hexadecimal characters")
        return SecretStr(raw.upper())

    @model_validator(mode="after")
    def key_matches_operation(self) -> "SecurityAccessCommand":
        if self.access_type == SecurityAccessType.REQUEST_SEED_LEVEL_1 and self.key is not None:
            raise ValueError("requestSeed must not contain a key")
        if self.access_type == SecurityAccessType.SEND_KEY_LEVEL_1 and self.key is None:
            raise ValueError("sendKey requires a key")
        return self


class SecurityAccessStateResponse(BaseModel):
    ecu_id: str
    security_level: int
    failed_attempts: int
    locked_until_ms: int | None
    challenge_active: bool
    seed_expires_at_ms: int | None
    security_version: int
    session_version: int
    simulation_time_ms: int


class RoutineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: int = Field(ge=0, le=0xFFFF)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    allowed_sessions: list[DiagnosticSessionType] = Field(min_length=1, max_length=3)
    execution_time_ms: int = Field(default=0, ge=0, le=600_000)
    supports_stop: bool = False
    result_template: RoutineParameters = Field(default_factory=dict)

    @field_validator("allowed_sessions")
    @classmethod
    def unique_sessions(cls, value: list[DiagnosticSessionType]) -> list[DiagnosticSessionType]:
        if len(set(value)) != len(value):
            raise ValueError("allowed_sessions must be unique")
        return value

    @field_validator("result_template")
    @classmethod
    def bounded_result_template(cls, value: RoutineParameters) -> RoutineParameters:
        if len(value) > 16:
            raise ValueError("result_template must contain at most 16 values")
        return value


class RoutineControlCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: CommandId
    control_type: RoutineControlType
    expected_session_version: int = Field(ge=1)
    expected_routine_version: int = Field(ge=1)
    parameters: RoutineParameters = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def bounded_parameters(cls, value: RoutineParameters) -> RoutineParameters:
        if len(value) > 16:
            raise ValueError("parameters must contain at most 16 values")
        return value

    @model_validator(mode="after")
    def parameters_only_on_start(self) -> "RoutineControlCommand":
        if self.control_type != RoutineControlType.START and self.parameters:
            raise ValueError("only startRoutine may contain parameters")
        return self


class RoutineResponse(BaseModel):
    id: UUID
    ecu_id: str
    identifier: int
    identifier_hex: str
    name: str
    description: str
    allowed_sessions: list[DiagnosticSessionType]
    execution_time_ms: int
    supports_stop: bool
    definition_version: int
    status: RoutineStatus
    invocation_count: int
    started_at_ms: int | None
    completes_at_ms: int | None
    stopped_at_ms: int | None
    routine_version: int
    created_at: datetime
    updated_at: datetime


class RoutinePage(BaseModel):
    items: list[RoutineResponse]
    total: int
    limit: int
    offset: int


class DidCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: int = Field(ge=0, le=0xFFFF)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    data_type: DidDataType
    unit: str = Field(default="", max_length=32)
    writable: bool = False
    readable_sessions: list[DiagnosticSessionType] = Field(min_length=1, max_length=3)
    writable_sessions: list[DiagnosticSessionType] = Field(default_factory=list, max_length=3)
    value: DidValue
    minimum: float | None = None
    maximum: float | None = None
    max_length: int | None = Field(default=None, ge=1, le=4096)

    @model_validator(mode="after")
    def validate_definition(self) -> "DidCreate":
        if len(set(self.readable_sessions)) != len(self.readable_sessions):
            raise ValueError("readable_sessions must be unique")
        if len(set(self.writable_sessions)) != len(self.writable_sessions):
            raise ValueError("writable_sessions must be unique")
        if not self.writable and self.writable_sessions:
            raise ValueError("read-only DIDs cannot declare writable_sessions")
        if self.writable and not self.writable_sessions:
            raise ValueError("writable DIDs require at least one writable session")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        if self.data_type not in {DidDataType.INTEGER, DidDataType.DECIMAL} and (
            self.minimum is not None or self.maximum is not None
        ):
            raise ValueError("only numeric DIDs may declare minimum or maximum")
        if self.data_type != DidDataType.STRING and self.max_length is not None:
            raise ValueError("only string DIDs may declare max_length")
        return self


class DidResponse(BaseModel):
    id: UUID
    ecu_id: str
    identifier: int
    identifier_hex: str
    name: str
    description: str
    data_type: DidDataType
    unit: str
    writable: bool
    readable_sessions: list[DiagnosticSessionType]
    writable_sessions: list[DiagnosticSessionType]
    value: DidValue
    minimum: float | None
    maximum: float | None
    max_length: int | None
    version: int
    created_at: datetime
    updated_at: datetime


class DidPage(BaseModel):
    items: list[DidResponse]
    total: int
    limit: int
    offset: int


class DidReadCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: CommandId
    identifiers: list[int] = Field(min_length=1, max_length=16)

    @field_validator("identifiers")
    @classmethod
    def valid_identifiers(cls, value: list[int]) -> list[int]:
        if any(identifier < 0 or identifier > 0xFFFF for identifier in value):
            raise ValueError("identifiers must be between 0 and 65535")
        if len(set(value)) != len(value):
            raise ValueError("identifiers must be unique")
        return value


class DidWriteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: CommandId
    expected_session_version: int = Field(ge=1)
    expected_did_version: int = Field(ge=1)
    value: DidValue


class DiagnosticSessionControlCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: CommandId
    expected_version: int = Field(ge=1)
    session_type: DiagnosticSessionType


class DiagnosticSessionResponse(BaseModel):
    ecu_id: str
    session_type: DiagnosticSessionType
    security_level: int
    version: int
    simulation_time_ms: int


class DiagnosticCommandResponse(BaseModel):
    command_id: str
    ecu_id: str
    service_id: int
    positive_response_service_id: int
    previous_version: int
    session_version: int
    result: dict[str, Any]
    duplicate: bool = False
    created_at: datetime


class DtcReportCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: DtcCode
    status_mask: int = Field(ge=0, le=255)
    severity: DtcSeverity = DtcSeverity.WARNING
    description: str = Field(default="", max_length=240)
    snapshot: dict[str, bool | int | float | str] = Field(default_factory=dict)

    @field_validator("snapshot")
    @classmethod
    def bounded_snapshot(
        cls, value: dict[str, bool | int | float | str]
    ) -> dict[str, bool | int | float | str]:
        if len(value) > 32:
            raise ValueError("snapshot must contain at most 32 values")
        return value


class DtcResponse(BaseModel):
    id: UUID
    ecu_id: str
    code: str
    status_mask: int
    severity: DtcSeverity
    description: str
    occurrence_count: int
    first_seen_ms: int
    last_seen_ms: int
    snapshot: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


class DtcPage(BaseModel):
    items: list[DtcResponse]
    total: int
    limit: int
    offset: int


class DtcClearCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: CommandId
    expected_version: int = Field(ge=1)
    group: DtcCode = "FFFFFF"


class DiagnosticTransport(StrEnum):
    LOCAL = "local"
    DOIP = "doip"


class DoipEnvelope(BaseModel):
    """Logical DoIP boundary; socket framing remains outside the domain service."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: int = Field(default=0x03, ge=0x02, le=0x03)
    source_address: int = Field(ge=0, le=0xFFFF)
    target_address: int = Field(ge=0, le=0xFFFF)
    routing_activation_type: int = Field(default=0, ge=0, le=0xFF)

    @model_validator(mode="after")
    def distinct_logical_addresses(self) -> "DoipEnvelope":
        if self.source_address == self.target_address:
            raise ValueError("DoIP source and target logical addresses must differ")
        return self


class ObdPid(IntEnum):
    ENGINE_COOLANT_TEMPERATURE = 0x05
    VEHICLE_SPEED = 0x0D
    CONTROL_MODULE_VOLTAGE = 0x42
    HYBRID_BATTERY_REMAINING_LIFE = 0x5B


class ObdMode01Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pids: list[ObdPid] = Field(min_length=1, max_length=16)

    @field_validator("pids")
    @classmethod
    def unique_pids(cls, value: list[ObdPid]) -> list[ObdPid]:
        if len(value) != len(set(value)):
            raise ValueError("OBD-II PIDs must be unique")
        return value


class ObdPidValue(BaseModel):
    pid: int
    pid_hex: str
    did_identifier: int
    name: str
    value: DidValue
    unit: str
    did_version: int


class ObdMode01Response(BaseModel):
    ecu_id: str
    mode: int = 0x01
    values: list[ObdPidValue]


class ObdMode03Response(BaseModel):
    ecu_id: str
    mode: int = 0x03
    dtcs: list[DtcResponse]


class DiagnosticCampaignStepType(StrEnum):
    OBD_MODE_01 = "obd_mode_01"
    OBD_MODE_03 = "obd_mode_03"
    UDS_READ_DIDS = "uds_read_dids"


class DiagnosticCampaignStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    step_type: DiagnosticCampaignStepType
    pids: list[ObdPid] = Field(default_factory=list, max_length=16)
    identifiers: list[int] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def operation_parameters(self) -> "DiagnosticCampaignStep":
        if self.step_type == DiagnosticCampaignStepType.OBD_MODE_01:
            if not self.pids or self.identifiers:
                raise ValueError("obd_mode_01 requires pids only")
            if len(self.pids) != len(set(self.pids)):
                raise ValueError("OBD-II PIDs must be unique")
        elif self.step_type == DiagnosticCampaignStepType.UDS_READ_DIDS:
            if not self.identifiers or self.pids:
                raise ValueError("uds_read_dids requires identifiers only")
            if len(self.identifiers) != len(set(self.identifiers)):
                raise ValueError("UDS identifiers must be unique")
            if any(identifier < 0 or identifier > 0xFFFF for identifier in self.identifiers):
                raise ValueError("UDS identifiers must fit in 16 bits")
        elif self.pids or self.identifiers:
            raise ValueError("obd_mode_03 does not accept pids or identifiers")
        return self


class DiagnosticCampaignCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: CommandId
    name: str = Field(min_length=1, max_length=80)
    transport: DiagnosticTransport = DiagnosticTransport.LOCAL
    doip: DoipEnvelope | None = None
    steps: list[DiagnosticCampaignStep] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def transport_boundary(self) -> "DiagnosticCampaignCommand":
        if self.transport == DiagnosticTransport.DOIP and self.doip is None:
            raise ValueError("DoIP transport requires a DoIP envelope")
        if self.transport == DiagnosticTransport.LOCAL and self.doip is not None:
            raise ValueError("local transport must not include a DoIP envelope")
        return self


class DiagnosticCampaignResponse(BaseModel):
    command_id: str
    ecu_id: str
    name: str
    transport: DiagnosticTransport
    doip: DoipEnvelope | None
    status: str
    step_count: int
    results: list[dict[str, Any]]
    duplicate: bool
    created_at: datetime
