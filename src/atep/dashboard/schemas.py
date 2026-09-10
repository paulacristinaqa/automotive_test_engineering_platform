from datetime import datetime

from pydantic import BaseModel, Field


class StatusCount(BaseModel):
    status: str
    count: int = Field(ge=0)


class DashboardKpis(BaseModel):
    test_runs_total: int = Field(ge=0)
    active_test_runs: int = Field(ge=0)
    test_cases_total: int = Field(ge=0)
    test_cases_passed: int = Field(ge=0)
    test_cases_failed: int = Field(ge=0)
    test_case_pass_rate: float | None = Field(ge=0, le=100)
    requirements_total: int = Field(ge=0)
    requirements_covered: int = Field(ge=0)
    requirement_coverage_rate: float | None = Field(ge=0, le=100)
    mutation_executions_total: int = Field(ge=0)
    average_mutation_score: float | None = Field(ge=0, le=100)
    automation_reports_total: int = Field(ge=0)
    dashboard_ai_evidence_total: int = Field(ge=0)


class DashboardEvidenceCard(BaseModel):
    projection_id: str
    subject_type: str
    subject_id: str
    status: str
    severity: str
    headline: str
    summary: str
    citations: list[str]
    created_at: datetime


class DashboardOverview(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_hours: int = Field(ge=1, le=720)
    kpis: DashboardKpis
    test_run_statuses: list[StatusCount]
    test_case_statuses: list[StatusCount]
    requirement_statuses: list[StatusCount]
    automation_outcomes: list[StatusCount]
    ai_evidence_severities: list[StatusCount]
    evidence_cards: list[DashboardEvidenceCard]
    contract_version: str = "dashboard-overview-v1"
    limitations: list[str]


class TestQualityTrendPoint(BaseModel):
    bucket_start: datetime
    test_runs_total: int = Field(ge=0)
    test_runs_passed: int = Field(ge=0)
    test_runs_failed: int = Field(ge=0)
    test_cases_total: int = Field(ge=0)
    test_cases_passed: int = Field(ge=0)
    test_cases_failed: int = Field(ge=0)
    test_case_pass_rate: float | None = Field(ge=0, le=100)


class TestQualityTrends(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_days: int = Field(ge=1, le=90)
    points: list[TestQualityTrendPoint]
    contract_version: str = "dashboard-test-quality-trends-v1"
    limitations: list[str]


class TestFailureDetail(BaseModel):
    result_id: str
    test_run_id: str
    run_id: str
    case_id: str
    definition_id: str
    suite: str
    attempt: int = Field(ge=0)
    duration_ms: int | None = Field(ge=0)
    observation: str | None = Field(max_length=500)
    observation_truncated: bool
    evidence_refs: list[str]
    failed_at: datetime


class TestFailurePage(BaseModel):
    items: list[TestFailureDetail]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    contract_version: str = "dashboard-test-failures-v1"
