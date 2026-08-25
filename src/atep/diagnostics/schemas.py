from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

CommandId = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
]
DtcCode = Annotated[str, StringConstraints(pattern=r"^[0-9A-F]{6}$")]
DidValue = bool | int | float | str


class UdsServiceId(IntEnum):
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    CLEAR_DIAGNOSTIC_INFORMATION = 0x14
    READ_DTC_INFORMATION = 0x19
    READ_DATA_BY_IDENTIFIER = 0x22
    WRITE_DATA_BY_IDENTIFIER = 0x2E


class UdsNegativeResponseCode(IntEnum):
    CONDITIONS_NOT_CORRECT = 0x22
    REQUEST_OUT_OF_RANGE = 0x31
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
