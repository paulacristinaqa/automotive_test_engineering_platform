from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AuditSearch(BaseModel):
    actor_user_id: UUID | None = None
    action: str | None = Field(default=None, min_length=1, max_length=160)
    resource_type: str | None = Field(default=None, min_length=1, max_length=80)
    resource_id: UUID | None = None
    outcome: str | None = Field(default=None, min_length=1, max_length=32)
    correlation_id: UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None

    @field_validator("action", "resource_type", "outcome")
    @classmethod
    def strip_filter(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("created_from", "created_to")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("audit timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.created_from is not None and self.created_to is not None:
            if self.created_from > self.created_to:
                raise ValueError("created_from must be earlier than or equal to created_to")
        return self


class AuditRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_user_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID
    outcome: str
    correlation_id: UUID | None
    details: dict[str, Any]
    created_at: datetime


class AuditRecordPage(BaseModel):
    items: list[AuditRecordResponse]
    total: int
    limit: int
    offset: int
