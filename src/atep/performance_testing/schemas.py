from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkloadType(StrEnum):
    PERFORMANCE = "performance"
    STRESS = "stress"


class ThresholdOperator(StrEnum):
    MAX = "max"
    MIN = "min"


class LoadStage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_seconds: int = Field(ge=1, le=900)
    virtual_users: int = Field(ge=1, le=500)
    requests_per_second: float = Field(gt=0, le=1000)


class MetricThreshold(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    operator: ThresholdOperator
    value: float = Field(ge=0)


class ResourceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cpu_cores: float = Field(gt=0, le=4)
    memory_mb: int = Field(ge=128, le=4096)
    gpu_allowed: bool = False

    @field_validator("gpu_allowed")
    @classmethod
    def gpu_must_be_disabled(cls, value: bool) -> bool:
        if value:
            raise ValueError("GPU use is not allowed by bounded performance profiles")
        return value


class PerformanceProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    workload_type: WorkloadType
    target: str = Field(min_length=1, max_length=200)
    stages: list[LoadStage] = Field(min_length=1, max_length=12)
    thresholds: list[MetricThreshold] = Field(min_length=1, max_length=20)
    resource_limits: ResourceLimits

    @model_validator(mode="after")
    def safe_totals_and_unique_thresholds(self) -> "PerformanceProfileCreate":
        if sum(stage.duration_seconds for stage in self.stages) > 3600:
            raise ValueError("total stage duration must not exceed 3600 seconds")
        keys = [(item.metric, item.operator) for item in self.thresholds]
        if len(keys) != len(set(keys)):
            raise ValueError("metric and operator threshold pairs must be unique")
        return self


class PerformanceProfileResponse(PerformanceProfileCreate):
    id: UUID
    version: int
    duplicate: bool = False
    created_by_user_id: UUID
    created_at: datetime


class PerformanceExecutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")
    test_run_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")
    baseline_execution_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")
    sample_count: int = Field(ge=1, le=10_000_000)
    duration_seconds: float = Field(gt=0, le=3600)
    metrics: dict[str, float] = Field(min_length=1, max_length=50)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)

    @field_validator("metrics")
    @classmethod
    def valid_metrics(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not key.isidentifier() or number < 0 for key, number in value.items()):
            raise ValueError("metrics require safe names and non-negative values")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def unique_refs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(not item or len(item) > 500 for item in value):
            raise ValueError("evidence references must be unique and bounded")
        return value


class PerformanceExecutionResponse(BaseModel):
    id: UUID
    execution_id: str
    profile_id: str
    profile_version: int
    test_run_id: str
    baseline_execution_id: str | None
    sample_count: int
    duration_seconds: float
    metrics: dict[str, float]
    threshold_results: list[dict[str, Any]]
    comparison: dict[str, Any] | None
    evidence_refs: list[str]
    outcome: str
    duplicate: bool = False
    recorded_by_user_id: UUID
    created_at: datetime


class PerformanceProfilePage(BaseModel):
    items: list[PerformanceProfileResponse]
    total: int
    limit: int
    offset: int


class PerformanceExecutionPage(BaseModel):
    items: list[PerformanceExecutionResponse]
    total: int
    limit: int
    offset: int
