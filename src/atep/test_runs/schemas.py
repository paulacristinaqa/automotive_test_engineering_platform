import re
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

if TYPE_CHECKING:
    from atep.test_runs.models import TestRun

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$")
ENVIRONMENT_PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{7,63}$")


class TestSuite(StrEnum):
    SMOKE = "smoke"
    REGRESSION = "regression"
    SANITY = "sanity"
    PERFORMANCE = "performance"
    STRESS = "stress"
    CUSTOM = "custom"


class TestRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TestRunCreate(BaseModel):
    run_id: str = Field(min_length=8, max_length=64)
    vehicle_id: str = Field(min_length=3, max_length=80)
    environment_profile_id: str | None = Field(default=None, min_length=8, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    suite: TestSuite
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        normalized = value.strip()
        if not RUN_ID_PATTERN.fullmatch(normalized):
            raise ValueError("test-run IDs must be URL-safe and contain 8 to 64 characters")
        return normalized

    @field_validator("vehicle_id", "name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("environment_profile_id")
    @classmethod
    def normalize_profile_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        if not ENVIRONMENT_PROFILE_ID_PATTERN.fullmatch(normalized):
            raise ValueError("environment profile IDs must be lowercase URL-safe slugs")
        return normalized


class TestRunStatusUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    status: TestRunStatus
    progress_percent: int = Field(ge=0, le=100)
    summary: str | None = Field(default=None, max_length=2000)

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_progress(self) -> "TestRunStatusUpdate":
        if self.status is TestRunStatus.QUEUED and self.progress_percent != 0:
            raise ValueError("queued test runs must have zero progress")
        if self.status is TestRunStatus.RUNNING and self.progress_percent >= 100:
            raise ValueError("running test runs must have progress between 0 and 99")
        if self.status in {TestRunStatus.PASSED, TestRunStatus.FAILED} and (
            self.progress_percent != 100
        ):
            raise ValueError("passed and failed test runs must have 100 percent progress")
        return self


class TestRunResponse(BaseModel):
    id: UUID
    run_id: str
    vehicle_id: str
    requested_by_user_id: UUID
    environment_profile_id: str | None
    environment_profile_version: int | None
    environment_snapshot: dict[str, Any] | None
    name: str
    suite: TestSuite
    metadata: dict[str, Any]
    status: TestRunStatus
    progress_percent: int
    version: int
    summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TestRunPage(BaseModel):
    items: list[TestRunResponse]
    total: int
    limit: int
    offset: int


class TestRunStreamEvent(BaseModel):
    type: str
    test_run: TestRunResponse
    occurred_at: datetime


def test_run_response(
    test_run: "TestRun", vehicle_identifier: str, environment_profile_identifier: str | None = None
) -> TestRunResponse:
    profile_id = environment_profile_identifier
    if profile_id is None and test_run.environment_snapshot is not None:
        snapshot_profile_id = test_run.environment_snapshot.get("profile_id")
        profile_id = str(snapshot_profile_id) if snapshot_profile_id is not None else None
    return TestRunResponse(
        id=test_run.id,
        run_id=test_run.run_id,
        vehicle_id=vehicle_identifier,
        requested_by_user_id=test_run.requested_by_user_id,
        environment_profile_id=profile_id,
        environment_profile_version=test_run.environment_profile_version,
        environment_snapshot=test_run.environment_snapshot,
        name=test_run.name,
        suite=test_run.suite,
        metadata=test_run.metadata_,
        status=test_run.status,
        progress_percent=test_run.progress_percent,
        version=test_run.version,
        summary=test_run.summary,
        started_at=test_run.started_at,
        completed_at=test_run.completed_at,
        created_at=test_run.created_at,
        updated_at=test_run.updated_at,
    )
