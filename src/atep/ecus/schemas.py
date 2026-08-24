import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

ECU_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
FAULT_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,31}$")


class EcuType(StrEnum):
    MOTOR = "motor"
    BATTERY = "battery"
    DOOR = "door"
    ABS = "abs"
    ADAS = "adas"
    CLIMATE = "climate"
    GATEWAY = "gateway"
    LIGHTING = "lighting"
    BODY = "body"


class EcuOperationalState(StrEnum):
    OFFLINE = "offline"
    BOOTING = "booting"
    RUNNING = "running"
    DEGRADED = "degraded"
    FAULT = "fault"
    SHUTDOWN = "shutdown"


class EcuFaultSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class EcuFaultStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class EcuMemoryCell(BaseModel):
    address: int = Field(ge=0, le=65_535)
    value: int = Field(ge=0, le=255)


class EcuFault(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    severity: EcuFaultSeverity
    status: EcuFaultStatus = EcuFaultStatus.PENDING
    description: str = Field(default="", max_length=200)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not FAULT_CODE_PATTERN.fullmatch(normalized):
            raise ValueError("fault codes must use uppercase letters, numbers, and underscores")
        return normalized

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        return value.strip()


class EcuStatePayload(BaseModel):
    operational_state: EcuOperationalState = EcuOperationalState.OFFLINE
    memory: list[EcuMemoryCell] = Field(default_factory=list, max_length=256)
    faults: list[EcuFault] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def require_unique_entries_and_consistent_fault_state(self) -> "EcuStatePayload":
        addresses = [cell.address for cell in self.memory]
        if len(addresses) != len(set(addresses)):
            raise ValueError("ECU memory addresses must be unique")
        codes = [fault.code for fault in self.faults]
        if len(codes) != len(set(codes)):
            raise ValueError("ECU fault codes must be unique")
        has_critical_fault = any(
            fault.severity is EcuFaultSeverity.CRITICAL
            and fault.status is EcuFaultStatus.CONFIRMED
            for fault in self.faults
        )
        if has_critical_fault and self.operational_state is not EcuOperationalState.FAULT:
            raise ValueError("a confirmed critical fault requires the ECU fault state")
        return self


class EcuCreate(EcuStatePayload):
    identifier: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    ecu_type: EcuType

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not ECU_IDENTIFIER_PATTERN.fullmatch(normalized):
            raise ValueError("ECU identifiers must use lowercase letters, numbers, and hyphens")
        return normalized

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        return value.strip()


class EcuStateReplace(EcuStatePayload):
    expected_version: int = Field(ge=1)


class EcuResponse(EcuStatePayload):
    id: UUID
    vehicle_id: str
    identifier: str
    display_name: str
    ecu_type: EcuType
    version: int
    created_at: datetime
    updated_at: datetime


class EcuPage(BaseModel):
    items: list[EcuResponse]
    total: int
    limit: int
    offset: int
