import re
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from atep.test_runs.schemas import ENVIRONMENT_PROFILE_ID_PATTERN, RUN_ID_PATTERN, TestSuite

if TYPE_CHECKING:
    from atep.test_jobs.models import TestJob

JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$")


class TestJobStatus(StrEnum):
    SCHEDULED = "scheduled"
    DISPATCHED = "dispatched"
    CANCELLED = "cancelled"


class TestJobCreate(BaseModel):
    job_id: str = Field(min_length=8, max_length=64)
    run_id: str = Field(min_length=8, max_length=64)
    vehicle_id: str = Field(min_length=3, max_length=80)
    environment_profile_id: str | None = Field(default=None, min_length=8, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    suite: TestSuite
    metadata: dict[str, Any] = Field(default_factory=dict)
    scheduled_for: datetime

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, value: str) -> str:
        value = value.strip()
        if not JOB_ID_PATTERN.fullmatch(value):
            raise ValueError("test-job IDs must be URL-safe and contain 8 to 64 characters")
        return value

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        value = value.strip()
        if not RUN_ID_PATTERN.fullmatch(value):
            raise ValueError("test-run IDs must be URL-safe and contain 8 to 64 characters")
        return value

    @field_validator("vehicle_id", "name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("environment_profile_id")
    @classmethod
    def normalize_profile_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().casefold()
        if not ENVIRONMENT_PROFILE_ID_PATTERN.fullmatch(value):
            raise ValueError("environment profile IDs must be lowercase URL-safe slugs")
        return value

    @field_validator("scheduled_for")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled_for must include a timezone offset")
        return value


class TestJobCancel(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class TestJobResponse(BaseModel):
    id: UUID
    job_id: str
    run_id: str
    vehicle_id: str
    requested_by_user_id: UUID
    environment_profile_id: str | None
    environment_profile_version: int | None
    environment_snapshot: dict[str, Any] | None
    name: str
    suite: TestSuite
    metadata: dict[str, Any]
    scheduled_for: datetime
    status: TestJobStatus
    version: int
    test_run_id: UUID | None
    dispatched_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime


class TestJobPage(BaseModel):
    items: list[TestJobResponse]
    total: int
    limit: int
    offset: int


def test_job_response(job: "TestJob", vehicle_identifier: str) -> TestJobResponse:
    profile_id = None
    if job.environment_snapshot is not None:
        profile_id = str(job.environment_snapshot.get("profile_id"))
    return TestJobResponse(
        id=job.id,
        job_id=job.job_id,
        run_id=job.run_id,
        vehicle_id=vehicle_identifier,
        requested_by_user_id=job.requested_by_user_id,
        environment_profile_id=profile_id,
        environment_profile_version=job.environment_profile_version,
        environment_snapshot=job.environment_snapshot,
        name=job.name,
        suite=job.suite,
        metadata=job.metadata_,
        scheduled_for=job.scheduled_for,
        status=job.status,
        version=job.version,
        test_run_id=job.test_run_id,
        dispatched_at=job.dispatched_at,
        cancelled_at=job.cancelled_at,
        cancellation_reason=job.cancellation_reason,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
