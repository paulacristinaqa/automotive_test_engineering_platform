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
    attempt_count: int
    duplicate: bool = False
    requested_by_user_id: UUID
    created_at: datetime


class AiAnalysisRequestPage(BaseModel):
    items: list[AiAnalysisRequestResponse]
    total: int
    limit: int
    offset: int


class AiAnalysisExecute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")
    provider_id: str = Field(default="local-rules", pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")


class AiFinding(BaseModel):
    code: str = Field(min_length=3, max_length=64, pattern=r"^[A-Z][A-Z0-9_]+$")
    severity: str = Field(pattern=r"^(info|low|medium|high|critical)$")
    message: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)


class AiAnalysisResult(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    findings: list[AiFinding] = Field(default_factory=list, max_length=50)
    recommendations: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0, le=1)

    @field_validator("recommendations")
    @classmethod
    def bounded_recommendations(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 1000 for item in value):
            raise ValueError("recommendations must contain 1 to 1000 characters")
        return value


class AiAnalysisExecutionResponse(BaseModel):
    id: UUID
    execution_id: str
    request_id: str
    attempt: int
    provider_id: str
    provider_kind: str
    status: str
    rule_version: str
    result: AiAnalysisResult
    error_code: str | None
    duplicate: bool = False
    executed_by_user_id: UUID
    started_at: datetime
    completed_at: datetime


class AiAnalysisExecutionPage(BaseModel):
    items: list[AiAnalysisExecutionResponse]
    total: int
    limit: int
    offset: int


class AiLogAnalysisCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")
    source: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    lines: list[str] = Field(min_length=1, max_length=500)

    @field_validator("lines")
    @classmethod
    def bounded_lines(cls, value: list[str]) -> list[str]:
        if any(not line or len(line.encode()) > 2000 for line in value):
            raise ValueError("log lines must contain 1 to 2000 encoded bytes")
        if sum(len(line.encode()) for line in value) > 256_000:
            raise ValueError("log batch must not exceed 256000 encoded bytes")
        return value


class AiLogEvent(BaseModel):
    line_number: int = Field(ge=1, le=500)
    timestamp: datetime
    level: str = Field(pattern=r"^(trace|debug|info|warning|error|critical)$")
    component: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=1000)
    cluster_id: str = Field(pattern=r"^[a-f0-9]{16}$")


class AiLogCluster(BaseModel):
    cluster_id: str
    count: int
    first_timestamp: datetime
    last_timestamp: datetime
    levels: list[str]
    representative: str
    line_numbers: list[int]


class AiLogAnomaly(BaseModel):
    anomaly_type: str
    severity: str
    cluster_id: str
    explanation: str
    line_numbers: list[int]


class AiFailureExplanation(BaseModel):
    summary: str
    supporting_line_numbers: list[int]
    evidence_refs: list[str]
    limitations: list[str]


class AiLogAnalysisResponse(BaseModel):
    id: UUID
    analysis_id: str
    request_id: str
    source: str
    line_count: int
    parsed_count: int
    rejected_count: int
    timeline: list[AiLogEvent]
    clusters: list[AiLogCluster]
    anomalies: list[AiLogAnomaly]
    explanation: AiFailureExplanation
    duplicate: bool = False
    created_by_user_id: UUID
    created_at: datetime


class AiLogAnalysisPage(BaseModel):
    items: list[AiLogAnalysisResponse]
    total: int
    limit: int
    offset: int


class AiTestSuggestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")
    requirement_refs: list[str] = Field(min_length=1, max_length=20)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    name: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=2000)
    domain: str = Field(
        pattern=r"^(core|digital_vehicle|ecu|can|diagnostics|electric_vehicle|adas|integration)$"
    )
    level: str = Field(pattern=r"^(unit|component|integration|system|end_to_end)$")
    automation_mode: str = Field(default="automated", pattern=r"^(automated|manual|hybrid)$")
    timeout_seconds: int = Field(default=300, ge=1, le=86400)

    @field_validator("requirement_refs", "evidence_refs")
    @classmethod
    def bounded_unique_refs(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > 500 for item in normalized):
            raise ValueError("references must contain 1 to 500 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("references must be unique")
        return normalized


class AiTestSuggestionReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    decision: str = Field(pattern=r"^(approve|reject)$")
    comment: str = Field(min_length=3, max_length=2000)


class AiTestSuggestionPromote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    definition_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")


class AiTestSuggestionResponse(BaseModel):
    id: UUID
    suggestion_id: str
    request_id: str
    requirement_refs: list[str]
    evidence_refs: list[str]
    candidate: dict[str, Any]
    rationale: str
    status: str
    version: int
    duplicate: bool = False
    created_by_user_id: UUID
    reviewed_by_user_id: UUID | None
    review_comment: str | None
    reviewed_at: datetime | None
    promoted_definition_id: UUID | None
    promoted_definition_external_id: str | None
    created_at: datetime
    updated_at: datetime


class AiTestSuggestionPage(BaseModel):
    items: list[AiTestSuggestionResponse]
    total: int
    limit: int
    offset: int
