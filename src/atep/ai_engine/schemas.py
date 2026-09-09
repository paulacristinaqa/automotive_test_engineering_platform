from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AiTask(StrEnum):
    LOG_ANALYSIS = "log_analysis"
    FAILURE_EXPLANATION = "failure_explanation"
    TEST_SUGGESTION = "test_suggestion"
    ROOT_CAUSE = "root_cause"
    RISK_ANALYSIS = "risk_analysis"


class AiSubjectType(StrEnum):
    TEST_RUN = "test_run"
    AUTOMATION_REPORT = "automation_report"
    FAULT_EXECUTION = "fault_execution"
    MUTATION_EXECUTION = "mutation_execution"


class ProviderPolicy(StrEnum):
    LOCAL_ONLY = "local_only"
    EXTERNAL_ALLOWED = "external_allowed"


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class AiAnalysisRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")
    task: AiTask
    subject_type: AiSubjectType
    subject_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$")
    provider_policy: ProviderPolicy = ProviderPolicy.LOCAL_ONLY
    data_classification: DataClassification = DataClassification.INTERNAL
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    context: dict[str, Any] = Field(default_factory=dict)
    instructions: str = Field(default="", max_length=2000)

    @field_validator("evidence_refs")
    @classmethod
    def unique_bounded_refs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence references must be unique")
        if any(not item or len(item) > 500 for item in value):
            raise ValueError("evidence references must contain 1 to 500 characters")
        return value

    @field_validator("context")
    @classmethod
    def bounded_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json

        if len(json.dumps(value, separators=(",", ":"), default=str).encode()) > 16_384:
            raise ValueError("context must not exceed 16384 bytes")
        return value


class AiAnalysisRequestResponse(BaseModel):
    id: UUID
    request_id: str
    task: AiTask
    subject_type: AiSubjectType
    subject_id: str
    provider_policy: ProviderPolicy
    data_classification: DataClassification
    evidence_refs: list[str]
    context: dict[str, Any]
    instructions: str
    status: str
    duplicate: bool = False
    requested_by_user_id: UUID
    created_at: datetime


class AiAnalysisRequestPage(BaseModel):
    items: list[AiAnalysisRequestResponse]
    total: int
    limit: int
    offset: int
