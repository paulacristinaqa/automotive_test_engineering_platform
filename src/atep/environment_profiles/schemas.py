import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")
MAX_CONFIGURATION_BYTES = 16_384


class VehicleKind(StrEnum):
    ELECTRIC = "electric"
    HYBRID = "hybrid"
    AUTONOMOUS = "autonomous"


class PropertySource(StrEnum):
    SIMULATOR = "simulator"
    AAOS = "aaos"


class EnvironmentProfileStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class EnvironmentProfileCreate(BaseModel):
    profile_id: str = Field(min_length=8, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    vehicle_kind: VehicleKind
    property_source: PropertySource
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not PROFILE_ID_PATTERN.fullmatch(normalized):
            raise ValueError("profile IDs must be lowercase URL-safe slugs of 8 to 64 characters")
        return normalized

    @field_validator("name", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def bound_configuration(self) -> "EnvironmentProfileCreate":
        _validate_configuration_size(self.configuration)
        return self


class EnvironmentProfileStatusUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    status: EnvironmentProfileStatus


class EnvironmentProfileResponse(BaseModel):
    id: UUID
    profile_id: str
    created_by_user_id: UUID
    name: str
    description: str
    vehicle_kind: VehicleKind
    property_source: PropertySource
    configuration: dict[str, Any]
    status: EnvironmentProfileStatus
    version: int
    created_at: datetime
    updated_at: datetime


class EnvironmentProfilePage(BaseModel):
    items: list[EnvironmentProfileResponse]
    total: int
    limit: int
    offset: int


def _validate_configuration_size(configuration: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(configuration, separators=(",", ":"), sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("configuration must contain JSON-compatible values") from exc
    if len(encoded) > MAX_CONFIGURATION_BYTES:
        raise ValueError(f"configuration must not exceed {MAX_CONFIGURATION_BYTES} bytes")
