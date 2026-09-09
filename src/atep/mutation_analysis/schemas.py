import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

PUBLIC_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")
REQUIREMENT_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]{2,79}$")
MAX_JSON_BYTES = 8_192


class MutationOperator(StrEnum):
    CONDITIONAL_NEGATION = "conditional_negation"
    BOUNDARY_SHIFT = "boundary_shift"
    ARITHMETIC_REPLACEMENT = "arithmetic_replacement"
    RETURN_VALUE_REPLACEMENT = "return_value_replacement"
    CONSTANT_REPLACEMENT = "constant_replacement"
    BOOLEAN_REPLACEMENT = "boolean_replacement"
    EXCEPTION_SUPPRESSION = "exception_suppression"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MutantStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    KILLED = "killed"
    SURVIVED = "survived"
    ERROR = "error"
    SKIPPED = "skipped"


class RequirementCriticality(StrEnum):
    QM = "qm"
    ASIL_A = "asil_a"
    ASIL_B = "asil_b"
    ASIL_C = "asil_c"
    ASIL_D = "asil_d"


class CoverageStatus(StrEnum):
    COVERED = "covered"
    PARTIAL = "partial"
    GAP = "gap"


class MutantDefinition(BaseModel):
    mutant_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    order: int = Field(ge=1, le=500)
    operator: MutationOperator
    target: str = Field(min_length=1, max_length=240)
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_detection: str = Field(min_length=1, max_length=500)
    required: bool = True

    @model_validator(mode="after")
    def bound_parameters(self) -> "MutantDefinition":
        _bound_json(self.parameters, "mutant parameters")
        return self


class MutationCampaignCreate(BaseModel):
    campaign_id: str = Field(min_length=8, max_length=64)
    catalog_suite_id: str = Field(min_length=8, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    mutants: list[MutantDefinition] = Field(min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("campaign_id", "catalog_suite_id")
    @classmethod
    def normalize_public_id(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not PUBLIC_ID_PATTERN.fullmatch(normalized):
            raise ValueError("IDs must be lowercase URL-safe slugs of 8 to 64 characters")
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
    def unique_mutants(self) -> "MutationCampaignCreate":
        identifiers = [item.mutant_id for item in self.mutants]
        orders = [item.order for item in self.mutants]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("mutant identifiers must be unique")
        if len(orders) != len(set(orders)):
            raise ValueError("mutant order values must be unique")
        return self


class CampaignStatusUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    status: CampaignStatus


class MutationCampaignResponse(BaseModel):
    id: UUID
    campaign_id: str
    created_by_user_id: UUID
    catalog_suite_id: str
    suite_version: int
    suite_snapshot: dict[str, Any]
    name: str
    description: str
    mutants: list[MutantDefinition]
    tags: list[str]
    status: CampaignStatus
    version: int
    created_at: datetime
    updated_at: datetime


class MutationCampaignPage(BaseModel):
    items: list[MutationCampaignResponse]
    total: int
    limit: int
    offset: int


class MutationExecutionCreate(BaseModel):
    execution_id: str = Field(min_length=8, max_length=64)
    vehicle_id: str = Field(min_length=3, max_length=80)
    test_run_id: str | None = Field(default=None, min_length=8, max_length=64)

    @field_validator("execution_id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not PUBLIC_ID_PATTERN.fullmatch(normalized):
            raise ValueError("execution ID must be a lowercase URL-safe slug")
        return normalized


class MutationExecutionResponse(BaseModel):
    id: UUID
    execution_id: str
    campaign_id: str
    campaign_version: int
    campaign_snapshot: dict[str, Any]
    vehicle_id: str
    test_run_id: str | None
    requested_by_user_id: UUID
    status: ExecutionStatus
    total_mutants: int
    completed_mutants: int
    killed_mutants: int
    survived_mutants: int
    mutation_score: float | None
    version: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MutationExecutionPage(BaseModel):
    items: list[MutationExecutionResponse]
    total: int
    limit: int
    offset: int


class MutantResultUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    status: MutantStatus
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    detected_by: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default_factory=list, max_length=200
    )
    evidence_refs: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def validate_terminal_result(self) -> "MutantResultUpdate":
        terminal = {
            MutantStatus.KILLED,
            MutantStatus.SURVIVED,
            MutantStatus.ERROR,
            MutantStatus.SKIPPED,
        }
        if self.status in terminal and self.duration_ms is None:
            raise ValueError("terminal mutant results require duration_ms")
        if self.status == MutantStatus.KILLED and not self.detected_by:
            raise ValueError("killed mutants require at least one detecting test")
        if self.status != MutantStatus.KILLED and self.detected_by:
            raise ValueError("detected_by is allowed only for killed mutants")
        return self


class MutantResultResponse(BaseModel):
    id: UUID
    execution_id: str
    mutant_id: str
    order: int
    operator: MutationOperator
    target: str
    required: bool
    status: MutantStatus
    duration_ms: int | None
    detected_by: list[str]
    evidence_refs: list[str]
    version: int
    created_at: datetime
    updated_at: datetime


class MutantResultPage(BaseModel):
    items: list[MutantResultResponse]
    total: int
    limit: int
    offset: int


class RequirementCoverageUpsert(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=240)
    criticality: RequirementCriticality
    definition_ids: list[Annotated[str, Field(min_length=8, max_length=64)]] = Field(
        default_factory=list, max_length=200
    )
    evidence_refs: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=20
    )

    @field_validator("definition_ids")
    @classmethod
    def normalize_definitions(cls, values: list[str]) -> list[str]:
        normalized = [item.strip().casefold() for item in values]
        if any(not PUBLIC_ID_PATTERN.fullmatch(item) for item in normalized):
            raise ValueError("definition IDs must be lowercase URL-safe slugs")
        if len(normalized) != len(set(normalized)):
            raise ValueError("definition IDs must be unique")
        return normalized


class RequirementCoverageResponse(BaseModel):
    id: UUID
    requirement_id: str
    managed_by_user_id: UUID
    title: str
    criticality: RequirementCriticality
    definition_ids: list[str]
    evidence_refs: list[str]
    status: CoverageStatus
    version: int
    created_at: datetime
    updated_at: datetime


class RequirementCoveragePage(BaseModel):
    items: list[RequirementCoverageResponse]
    total: int
    gaps: int
    partial: int
    covered: int
    limit: int
    offset: int


def coverage_status(definition_ids: list[str], evidence_refs: list[str]) -> CoverageStatus:
    if definition_ids and evidence_refs:
        return CoverageStatus.COVERED
    if definition_ids or evidence_refs:
        return CoverageStatus.PARTIAL
    return CoverageStatus.GAP


def _bound_json(value: Any, label: str) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite JSON") from exc
    if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError(f"{label} must not exceed {MAX_JSON_BYTES} bytes")
