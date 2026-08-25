from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

CommandId = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
]
DtcCode = Annotated[str, StringConstraints(pattern=r"^[0-9A-F]{6}$")]


class UdsServiceId(IntEnum):
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    CLEAR_DIAGNOSTIC_INFORMATION = 0x14
    READ_DTC_INFORMATION = 0x19


class UdsNegativeResponseCode(IntEnum):
    CONDITIONS_NOT_CORRECT = 0x22
    REQUEST_OUT_OF_RANGE = 0x31


class DiagnosticSessionType(StrEnum):
    DEFAULT = "default"
    PROGRAMMING = "programming"
    EXTENDED = "extended"


class DtcSeverity(StrEnum):
    INFORMATION = "information"
    WARNING = "warning"
    CRITICAL = "critical"


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
