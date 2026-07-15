import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

ROLE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,79}$")


def normalize_role_name(value: str) -> str:
    return value.strip().casefold()


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=255)
    permissions: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = normalize_role_name(value)
        if not ROLE_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("role names must use lowercase letters, numbers, and hyphens")
        return normalized

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("permissions")
    @classmethod
    def normalize_permissions(cls, value: list[str]) -> list[str]:
        return sorted({item.strip().casefold() for item in value})


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_role_name(value)
        if not ROLE_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("role names must use lowercase letters, numbers, and hyphens")
        return normalized

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "RoleUpdate":
        if self.name is None and self.description is None:
            raise ValueError("at least one role field must be provided")
        return self


class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: str
    permissions: list[str]
    created_at: datetime
    updated_at: datetime


class RolePage(BaseModel):
    items: list[RoleResponse]
    total: int
    limit: int
    offset: int


class PermissionResponse(BaseModel):
    id: UUID
    name: str
    description: str
