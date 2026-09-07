import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

CATALOG_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")
MAX_PARAMETERS_BYTES = 8_192


class TestDomain(StrEnum):
    CORE = "core"
    DIGITAL_VEHICLE = "digital_vehicle"
    ECU = "ecu"
    CAN = "can"
    DIAGNOSTICS = "diagnostics"
    ELECTRIC_VEHICLE = "electric_vehicle"
    ADAS = "adas"
    INTEGRATION = "integration"


class TestLevel(StrEnum):
    UNIT = "unit"
    COMPONENT = "component"
    INTEGRATION = "integration"
    SYSTEM = "system"
    END_TO_END = "end_to_end"


class AutomationMode(StrEnum):
    AUTOMATED = "automated"
    MANUAL = "manual"
    HYBRID = "hybrid"


class CatalogStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class SuiteType(StrEnum):
    SMOKE = "smoke"
    SANITY = "sanity"
    REGRESSION = "regression"
    PERFORMANCE = "performance"
    STRESS = "stress"
    SAFETY = "safety"


class TestStep(BaseModel):
    step_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    action: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=120)
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def bound_inputs(self) -> "TestStep":
        _bound_json(self.inputs, "step inputs")
        return self


class TestDefinitionCreate(BaseModel):
    definition_id: str = Field(min_length=8, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    domain: TestDomain
    level: TestLevel
    automation_mode: AutomationMode = AutomationMode.AUTOMATED
    timeout_seconds: int = Field(default=300, ge=1, le=86_400)
    tags: list[str] = Field(default_factory=list, max_length=20)
    preconditions: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=20
    )
    steps: list[TestStep] = Field(min_length=1, max_length=100)

    @field_validator("definition_id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not CATALOG_ID_PATTERN.fullmatch(normalized):
            raise ValueError("catalog IDs must be lowercase URL-safe slugs of 8 to 64 characters")
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
    def step_ids_are_unique(self) -> "TestDefinitionCreate":
        identifiers = [item.step_id for item in self.steps]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("test step identifiers must be unique")
        return self


class CatalogStatusUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    status: CatalogStatus


class TestDefinitionResponse(BaseModel):
    id: UUID
    definition_id: str
    created_by_user_id: UUID
    name: str
    description: str
    domain: TestDomain
    level: TestLevel
    automation_mode: AutomationMode
    timeout_seconds: int
    tags: list[str]
    preconditions: list[str]
    steps: list[TestStep]
    status: CatalogStatus
    version: int
    created_at: datetime
    updated_at: datetime


class TestDefinitionPage(BaseModel):
    items: list[TestDefinitionResponse]
    total: int
    limit: int
    offset: int


class TestSuiteItemCreate(BaseModel):
    definition_id: str = Field(min_length=8, max_length=64)
    order: int = Field(ge=1, le=1_000)
    required: bool = True
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("definition_id")
    @classmethod
    def normalize_definition_id(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not CATALOG_ID_PATTERN.fullmatch(normalized):
            raise ValueError("catalog IDs must be lowercase URL-safe slugs of 8 to 64 characters")
        return normalized

    @model_validator(mode="after")
    def bound_parameters(self) -> "TestSuiteItemCreate":
        _bound_json(self.parameter_overrides, "parameter overrides")
        return self


class TestSuiteCreate(BaseModel):
    suite_id: str = Field(min_length=8, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    suite_type: SuiteType
    cases: list[TestSuiteItemCreate] = Field(min_length=1, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("suite_id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not CATALOG_ID_PATTERN.fullmatch(normalized):
            raise ValueError("catalog IDs must be lowercase URL-safe slugs of 8 to 64 characters")
        return normalized

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
    def composition_is_unambiguous(self) -> "TestSuiteCreate":
        definitions = [item.definition_id for item in self.cases]
        orders = [item.order for item in self.cases]
        if len(definitions) != len(set(definitions)):
            raise ValueError("a test definition can appear only once in a suite")
        if len(orders) != len(set(orders)):
            raise ValueError("suite case order values must be unique")
        return self


class TestSuiteItemResponse(TestSuiteItemCreate):
    definition_version: int = Field(ge=1)
    name: str


class TestSuiteResponse(BaseModel):
    id: UUID
    suite_id: str
    created_by_user_id: UUID
    name: str
    description: str
    suite_type: SuiteType
    cases: list[TestSuiteItemResponse]
    tags: list[str]
    status: CatalogStatus
    version: int
    created_at: datetime
    updated_at: datetime


class TestSuitePage(BaseModel):
    items: list[TestSuiteResponse]
    total: int
    limit: int
    offset: int


def _bound_json(value: dict[str, Any], label: str) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain JSON-compatible values") from exc
    if len(encoded) > MAX_PARAMETERS_BYTES:
        raise ValueError(f"{label} must not exceed {MAX_PARAMETERS_BYTES} bytes")
