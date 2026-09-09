from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class CarSystemUiSurface(StrEnum):
    DASHBOARD = "dashboard"
    TEST_DETAIL = "test_detail"
    ALERTS = "alerts"


class ConnectionState(StrEnum):
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    OFFLINE = "offline"


class AutomationOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


EvidenceId = Annotated[
    str, Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]+$")
]


class CarSystemUiObservation(BaseModel):
    observation_id: EvidenceId
    surface: CarSystemUiSurface
    connection_state: ConnectionState
    displayed_run_status: RunStatus
    displayed_run_version: int = Field(ge=1)
    client_version: str = Field(min_length=1, max_length=64)
    captured_at: datetime
    evidence_ref: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_timezone(self) -> "CarSystemUiObservation":
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("CarSystemUI observation timestamps must include a UTC offset")
        return self


class AutomationReportCreate(BaseModel):
    report_id: str = Field(min_length=8, max_length=64)
    vehicle_id: str = Field(min_length=3, max_length=80)
    test_run_id: EvidenceId
    gateway_module_id: UUID
    fault_execution_id: EvidenceId | None = None
    mutation_execution_id: EvidenceId | None = None
    telemetry_event_ids: list[EvidenceId] = Field(min_length=1, max_length=100)
    vehicle_command_ids: list[EvidenceId] = Field(default_factory=list, max_length=100)
    carsystemui_observations: list[CarSystemUiObservation] = Field(min_length=1, max_length=50)

    @field_validator("report_id")
    @classmethod
    def normalize_report_id(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if (
            not normalized
            or not normalized[0].isalnum()
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in normalized
            )
        ):
            raise ValueError("report ID must be a lowercase URL-safe slug")
        return normalized

    @model_validator(mode="after")
    def unique_evidence(self) -> "AutomationReportCreate":
        collections = (
            self.telemetry_event_ids,
            self.vehicle_command_ids,
            [item.observation_id for item in self.carsystemui_observations],
        )
        if any(len(items) != len(set(items)) for items in collections):
            raise ValueError("cross-platform evidence identifiers must be unique")
        return self


class AutomationReportSummary(BaseModel):
    test_run_status: RunStatus
    test_run_version: int = Field(ge=1)
    fault_execution_status: str | None
    mutation_execution_status: str | None
    mutation_score: float | None = Field(default=None, ge=0, le=1)
    telemetry_event_count: int = Field(ge=1, le=100)
    vehicle_command_count: int = Field(ge=0, le=100)
    carsystemui_observation_count: int = Field(ge=1, le=50)
    connected_observation_count: int = Field(ge=0, le=50)


class AutomationReportResponse(BaseModel):
    id: UUID
    report_id: str
    vehicle_id: str
    test_run_id: str
    gateway_module_id: UUID
    fault_execution_id: str | None
    mutation_execution_id: str | None
    telemetry_event_ids: list[str]
    vehicle_command_ids: list[str]
    carsystemui_observations: list[CarSystemUiObservation]
    outcome: AutomationOutcome
    summary: AutomationReportSummary
    duplicate: bool = False
    created_by_user_id: UUID
    created_at: datetime


class AutomationReportPage(BaseModel):
    items: list[AutomationReportResponse]
    total: int
    limit: int
    offset: int
