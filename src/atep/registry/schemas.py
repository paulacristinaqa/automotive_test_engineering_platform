import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

MODULE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
CAPABILITY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$")
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


class ModuleStatus(StrEnum):
    REGISTERED = "registered"
    ACTIVE = "active"
    DEGRADED = "degraded"
    INACTIVE = "inactive"


def _validate_version(value: str) -> str:
    normalized = value.strip()
    if not VERSION_PATTERN.fullmatch(normalized):
        raise ValueError("versions must use semantic version syntax")
    return normalized


def normalize_capability_name(value: str) -> str:
    normalized = value.strip().casefold()
    if not CAPABILITY_NAME_PATTERN.fullmatch(normalized):
        raise ValueError("capability names must use dot-separated lowercase segments")
    return normalized


class CapabilityDeclaration(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    version: str = Field(max_length=32)
    description: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_capability_name(value)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        return _validate_version(value)

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        return value.strip()


class CapabilityUpdate(BaseModel):
    version: str = Field(max_length=32)
    description: str = Field(default="", max_length=500)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        return _validate_version(value)

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        return value.strip()


class ModuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    version: str = Field(max_length=32)
    base_url: HttpUrl | None = None
    capabilities: list[CapabilityDeclaration] = Field(default_factory=list, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not MODULE_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("module names must use lowercase letters, numbers, and hyphens")
        return normalized

    @field_validator("display_name", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        return _validate_version(value)

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, value: list[CapabilityDeclaration]) -> list[CapabilityDeclaration]:
        names = [item.name for item in value]
        if len(names) != len(set(names)):
            raise ValueError("capability names must be unique within a module")
        return sorted(value, key=lambda item: item.name)


class ModuleUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    version: str | None = Field(default=None, max_length=32)
    base_url: HttpUrl | None = None
    status: ModuleStatus | None = None

    @field_validator("display_name", "description")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str | None) -> str | None:
        return _validate_version(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "ModuleUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one module field must be provided")
        if self.status in {ModuleStatus.ACTIVE, ModuleStatus.DEGRADED}:
            raise ValueError("active and degraded status must be reported by module heartbeat")
        return self


class ModuleCredentialCommand(BaseModel):
    lease_duration_seconds: int = Field(default=60, ge=5, le=3600)


class ModuleCredentialResponse(BaseModel):
    module_id: UUID
    module_token: str
    lease_duration_seconds: int


class ModuleHeartbeat(BaseModel):
    status: ModuleStatus = ModuleStatus.ACTIVE
    version: str | None = Field(default=None, max_length=32)

    @field_validator("status")
    @classmethod
    def validate_operational_status(cls, value: ModuleStatus) -> ModuleStatus:
        if value not in {ModuleStatus.ACTIVE, ModuleStatus.DEGRADED}:
            raise ValueError("heartbeat status must be active or degraded")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str | None) -> str | None:
        return _validate_version(value) if value is not None else None


class CapabilityResponse(BaseModel):
    id: UUID
    name: str
    version: str
    description: str
    created_at: datetime
    updated_at: datetime


class ModuleResponse(BaseModel):
    id: UUID
    name: str
    display_name: str
    description: str
    version: str
    base_url: str | None
    status: ModuleStatus
    last_seen_at: datetime | None
    lease_expires_at: datetime | None
    lease_duration_seconds: int
    capabilities: list[CapabilityResponse]
    created_at: datetime
    updated_at: datetime


class ModulePage(BaseModel):
    items: list[ModuleResponse]
    total: int
    limit: int
    offset: int
