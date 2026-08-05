import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

VEHICLE_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
EVENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$")
PROPERTY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")

type TelemetryValue = bool | int | float | str
type CommandValue = bool | int | float | str


class VehicleStatus(StrEnum):
    REGISTERED = "registered"
    ACTIVE = "active"
    INACTIVE = "inactive"


class VehicleCommandKind(StrEnum):
    SET_PROPERTY = "set_property"


class VehicleCommandStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class VehicleCommandOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class VehicleCreate(BaseModel):
    identifier: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    model: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=500)

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not VEHICLE_IDENTIFIER_PATTERN.fullmatch(normalized):
            raise ValueError("vehicle identifiers must use lowercase letters, numbers, and hyphens")
        return normalized

    @field_validator("display_name", "model", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class VehicleStatusUpdate(BaseModel):
    status: VehicleStatus


class VehicleResponse(BaseModel):
    id: UUID
    identifier: str
    display_name: str
    model: str
    description: str
    status: VehicleStatus
    created_at: datetime
    updated_at: datetime


class VehiclePage(BaseModel):
    items: list[VehicleResponse]
    total: int
    limit: int
    offset: int


class TelemetryIngest(BaseModel):
    event_id: str = Field(min_length=8, max_length=64)
    property: str = Field(min_length=1, max_length=120)
    value: TelemetryValue
    unit: str | None = Field(default=None, max_length=40)
    timestamp: datetime
    source: str = Field(default="android-automotive", min_length=1, max_length=80)

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, value: str) -> str:
        normalized = value.strip()
        if not EVENT_ID_PATTERN.fullmatch(normalized):
            raise ValueError("event IDs must be URL-safe and contain 8 to 64 characters")
        return normalized

    @field_validator("property")
    @classmethod
    def validate_property(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not PROPERTY_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("property names must use lowercase snake_case segments")
        return normalized

    @field_validator("unit", "source")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_timezone(self) -> "TelemetryIngest":
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("telemetry timestamps must include a UTC offset")
        return self


class TelemetryResponse(BaseModel):
    id: UUID
    event_id: str
    vehicle_id: str
    source_module_id: UUID
    source: str
    property: str
    value: TelemetryValue
    unit: str | None
    timestamp: datetime
    received_at: datetime
    duplicate: bool = False


class TelemetryPage(BaseModel):
    items: list[TelemetryResponse]
    total: int
    limit: int
    offset: int


class VehicleCommandParameters(BaseModel):
    property: str = Field(min_length=1, max_length=120)
    value: CommandValue

    @field_validator("property")
    @classmethod
    def validate_property(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not PROPERTY_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("property names must use lowercase snake_case segments")
        return normalized


class VehicleCommandCreate(BaseModel):
    command_id: str = Field(min_length=8, max_length=64)
    target_module_id: UUID
    test_run_id: str | None = Field(default=None, min_length=8, max_length=64)
    kind: VehicleCommandKind = VehicleCommandKind.SET_PROPERTY
    parameters: VehicleCommandParameters
    available_at: datetime | None = None

    @field_validator("command_id", "test_run_id")
    @classmethod
    def validate_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not EVENT_ID_PATTERN.fullmatch(normalized):
            raise ValueError(
                "command and test-run IDs must be URL-safe and contain 8 to 64 characters"
            )
        return normalized

    @model_validator(mode="after")
    def require_available_at_timezone(self) -> "VehicleCommandCreate":
        if self.available_at is not None and (
            self.available_at.tzinfo is None or self.available_at.utcoffset() is None
        ):
            raise ValueError("command availability timestamps must include a UTC offset")
        return self


class VehicleCommandClaim(BaseModel):
    lease_seconds: int = Field(default=60, ge=10, le=300)


class VehicleCommandAcknowledge(BaseModel):
    claim_token: str = Field(min_length=32, max_length=128)
    outcome: VehicleCommandOutcome
    result: dict[str, CommandValue] | None = None
    error_code: str | None = Field(default=None, min_length=1, max_length=80)
    error_message: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("error_code", "error_message")
    @classmethod
    def strip_error(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_outcome_details(self) -> "VehicleCommandAcknowledge":
        if self.outcome is VehicleCommandOutcome.SUCCEEDED:
            if self.error_code is not None or self.error_message is not None:
                raise ValueError("successful commands cannot contain error details")
        elif self.error_code is None or self.error_message is None:
            raise ValueError("failed and rejected commands require an error code and message")
        return self


class VehicleCommandResponse(BaseModel):
    id: UUID
    command_id: str
    vehicle_id: str
    target_module_id: UUID
    requested_by_user_id: UUID
    test_run_id: str | None
    kind: VehicleCommandKind
    parameters: VehicleCommandParameters
    status: VehicleCommandStatus
    attempt_count: int
    available_at: datetime
    leased_until: datetime | None
    completed_at: datetime | None
    result: dict[str, CommandValue] | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class VehicleCommandDelivery(VehicleCommandResponse):
    claim_token: str


class VehicleCommandPage(BaseModel):
    items: list[VehicleCommandResponse]
    total: int
    limit: int
    offset: int
