import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

CAMPAIGN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")
STEP_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")
MAX_PARAMETERS_BYTES = 8_192
MAX_METADATA_BYTES = 8_192
MAX_CAMPAIGN_DURATION_MS = 1_800_000


class FaultDomain(StrEnum):
    DIGITAL_VEHICLE = "digital_vehicle"
    ECU = "ecu"
    CAN = "can"
    DIAGNOSTICS = "diagnostics"
    ELECTRIC_VEHICLE = "electric_vehicle"
    ADAS = "adas"


class FaultAction(StrEnum):
    SENSOR_STUCK = "sensor_stuck"
    SENSOR_OFFSET = "sensor_offset"
    COMPONENT_UNAVAILABLE = "component_unavailable"
    ECU_FAULT_OBSERVATION = "ecu_fault_observation"
    ECU_MEMORY_CORRUPTION = "ecu_memory_corruption"
    CAN_FRAME_DROP = "can_frame_drop"
    CAN_BIT_ERROR = "can_bit_error"
    CAN_BUS_OFF = "can_bus_off"
    DIAGNOSTIC_NEGATIVE_RESPONSE = "diagnostic_negative_response"
    DIAGNOSTIC_TIMEOUT = "diagnostic_timeout"
    BATTERY_OVERTEMPERATURE = "battery_overtemperature"
    CHARGING_FAULT = "charging_fault"
    INVERTER_DERATING = "inverter_derating"
    PERCEPTION_DROPOUT = "perception_dropout"
    PERCEPTION_MISCLASSIFICATION = "perception_misclassification"


ALLOWED_ACTIONS: dict[FaultDomain, frozenset[FaultAction]] = {
    FaultDomain.DIGITAL_VEHICLE: frozenset(
        {FaultAction.SENSOR_STUCK, FaultAction.SENSOR_OFFSET, FaultAction.COMPONENT_UNAVAILABLE}
    ),
    FaultDomain.ECU: frozenset(
        {FaultAction.ECU_FAULT_OBSERVATION, FaultAction.ECU_MEMORY_CORRUPTION}
    ),
    FaultDomain.CAN: frozenset(
        {FaultAction.CAN_FRAME_DROP, FaultAction.CAN_BIT_ERROR, FaultAction.CAN_BUS_OFF}
    ),
    FaultDomain.DIAGNOSTICS: frozenset(
        {FaultAction.DIAGNOSTIC_NEGATIVE_RESPONSE, FaultAction.DIAGNOSTIC_TIMEOUT}
    ),
    FaultDomain.ELECTRIC_VEHICLE: frozenset(
        {
            FaultAction.BATTERY_OVERTEMPERATURE,
            FaultAction.CHARGING_FAULT,
            FaultAction.INVERTER_DERATING,
        }
    ),
    FaultDomain.ADAS: frozenset(
        {FaultAction.PERCEPTION_DROPOUT, FaultAction.PERCEPTION_MISCLASSIFICATION}
    ),
}


class BlastRadius(StrEnum):
    SINGLE_COMPONENT = "single_component"
    SINGLE_NETWORK = "single_network"
    SINGLE_VEHICLE = "single_vehicle"


class FaultCampaignStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class FaultExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FaultStepStatus(StrEnum):
    PENDING = "pending"
    INJECTING = "injecting"
    INJECTED = "injected"
    RECOVERING = "recovering"
    RECOVERED = "recovered"
    FAILED = "failed"
    SKIPPED = "skipped"


class RecoveryPlan(BaseModel):
    action: str = Field(min_length=1, max_length=160)
    timeout_ms: int = Field(ge=1, le=600_000)
    verification: str = Field(min_length=1, max_length=500)

    @field_validator("action", "verification")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class FaultCampaignStep(BaseModel):
    step_id: str = Field(min_length=3, max_length=64)
    order: int = Field(ge=1, le=1_000)
    domain: FaultDomain
    action: FaultAction
    target_id: str = Field(min_length=1, max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = Field(ge=1, le=600_000)
    expected_effect: str = Field(min_length=1, max_length=500)
    recovery: RecoveryPlan
    required: bool = True

    @field_validator("step_id")
    @classmethod
    def validate_step_id(cls, value: str) -> str:
        normalized = value.strip()
        if not STEP_ID_PATTERN.fullmatch(normalized):
            raise ValueError("fault step IDs must be URL-safe and contain 3 to 64 characters")
        return normalized

    @field_validator("target_id", "expected_effect")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_action_and_parameters(self) -> "FaultCampaignStep":
        if self.action not in ALLOWED_ACTIONS[self.domain]:
            raise ValueError("fault action is not allowed for the selected domain")
        _bound_json(self.parameters, MAX_PARAMETERS_BYTES, "fault parameters")
        return self


class FaultCampaignCreate(BaseModel):
    campaign_id: str = Field(min_length=8, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    blast_radius: BlastRadius
    steps: list[FaultCampaignStep] = Field(min_length=1, max_length=32)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("campaign_id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not CAMPAIGN_ID_PATTERN.fullmatch(normalized):
            raise ValueError("campaign IDs must be lowercase URL-safe slugs of 8 to 64 characters")
        return normalized

    @field_validator("name", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized = [item.strip().casefold() for item in values]
        if any(not item or len(item) > 40 for item in normalized):
            raise ValueError("tags must contain 1 to 40 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("tags must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_steps(self) -> "FaultCampaignCreate":
        identifiers = [item.step_id for item in self.steps]
        orders = [item.order for item in self.steps]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("fault step identifiers must be unique")
        if len(orders) != len(set(orders)):
            raise ValueError("fault step order values must be unique")
        if sum(item.duration_ms + item.recovery.timeout_ms for item in self.steps) > (
            MAX_CAMPAIGN_DURATION_MS
        ):
            raise ValueError(
                "fault campaign duration and recovery budget must not exceed 1800000 ms"
            )
        return self


class FaultCampaignStatusUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    status: FaultCampaignStatus


class FaultCampaignResponse(BaseModel):
    id: UUID
    campaign_id: str
    created_by_user_id: UUID
    name: str
    description: str
    blast_radius: BlastRadius
    steps: list[FaultCampaignStep]
    tags: list[str]
    status: FaultCampaignStatus
    version: int
    created_at: datetime
    updated_at: datetime


class FaultCampaignPage(BaseModel):
    items: list[FaultCampaignResponse]
    total: int
    limit: int
    offset: int


class FaultExecutionCreate(BaseModel):
    execution_id: str = Field(min_length=8, max_length=64)
    vehicle_id: str = Field(min_length=3, max_length=80)
    test_run_id: str | None = Field(default=None, min_length=8, max_length=64)
    seed: int = Field(default=0, ge=0, le=2_147_483_647)
    dry_run: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("execution_id")
    @classmethod
    def normalize_execution_id(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not CAMPAIGN_ID_PATTERN.fullmatch(normalized):
            raise ValueError("execution IDs must be lowercase URL-safe slugs of 8 to 64 characters")
        return normalized

    @field_validator("vehicle_id", "test_run_id")
    @classmethod
    def strip_identifiers(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def bound_metadata(self) -> "FaultExecutionCreate":
        _bound_json(self.metadata, MAX_METADATA_BYTES, "execution metadata")
        return self


class FaultStepResultUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    status: FaultStepStatus
    attempt: int = Field(ge=1, le=100)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    observed_effect: str | None = Field(default=None, max_length=4_000)
    evidence_refs: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=20
    )

    @field_validator("observed_effect")
    @classmethod
    def strip_observation(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_terminal_evidence(self) -> "FaultStepResultUpdate":
        if (
            self.status
            in {
                FaultStepStatus.RECOVERED,
                FaultStepStatus.FAILED,
                FaultStepStatus.SKIPPED,
            }
            and self.duration_ms is None
        ):
            raise ValueError("terminal fault step results require duration_ms")
        return self


class FaultExecutionCancel(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class FaultStepResultResponse(BaseModel):
    id: UUID
    execution_id: str
    step_id: str
    order: int
    domain: FaultDomain
    action: FaultAction
    target_id: str
    required: bool
    status: FaultStepStatus
    attempt: int
    duration_ms: int | None
    observed_effect: str | None
    evidence_refs: list[str]
    version: int
    created_at: datetime
    updated_at: datetime


class FaultStepResultPage(BaseModel):
    items: list[FaultStepResultResponse]
    total: int
    limit: int
    offset: int


class FaultExecutionResponse(BaseModel):
    id: UUID
    execution_id: str
    campaign_id: str
    campaign_version: int
    campaign_snapshot: dict[str, Any]
    vehicle_id: str
    test_run_id: str | None
    requested_by_user_id: UUID
    seed: int
    dry_run: bool
    metadata: dict[str, Any]
    status: FaultExecutionStatus
    progress_percent: int
    version: int
    summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FaultExecutionPage(BaseModel):
    items: list[FaultExecutionResponse]
    total: int
    limit: int
    offset: int


def _bound_json(value: dict[str, Any], maximum: int, label: str) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain JSON-compatible values") from exc
    if len(encoded) > maximum:
        raise ValueError(f"{label} must not exceed {maximum} bytes")
