from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AiAnalysisRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_analysis_requests"
    __table_args__ = (UniqueConstraint("request_id", name="uq_ai_analysis_requests_request_id"),)

    request_id: Mapped[str] = mapped_column(String(64), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    task: Mapped[str] = mapped_column(String(32), index=True)
    subject_type: Mapped[str] = mapped_column(String(32), index=True)
    subject_id: Mapped[str] = mapped_column(String(80), index=True)
    provider_policy: Mapped[str] = mapped_column(String(32), index=True)
    data_classification: Mapped[str] = mapped_column(String(24), index=True)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON)
    context: Mapped[dict[str, Any]] = mapped_column(JSON)
    instructions: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), index=True, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)


class AiAnalysisExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_analysis_executions"
    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_ai_analysis_executions_execution_id"),
        UniqueConstraint("request_id", "attempt", name="uq_ai_analysis_execution_attempt"),
    )

    execution_id: Mapped[str] = mapped_column(String(64), index=True)
    execution_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_analysis_requests.id", ondelete="CASCADE"), index=True
    )
    executed_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    attempt: Mapped[int] = mapped_column(Integer)
    provider_id: Mapped[str] = mapped_column(String(64), index=True)
    provider_kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    rule_version: Mapped[str] = mapped_column(String(32))
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AiLogAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_log_analyses"
    __table_args__ = (
        UniqueConstraint("analysis_id", name="uq_ai_log_analyses_analysis_id"),
        UniqueConstraint("request_id", name="uq_ai_log_analyses_request_id"),
    )

    analysis_id: Mapped[str] = mapped_column(String(64), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_analysis_requests.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    source: Mapped[str] = mapped_column(String(80), index=True)
    line_count: Mapped[int] = mapped_column(Integer)
    parsed_count: Mapped[int] = mapped_column(Integer)
    rejected_count: Mapped[int] = mapped_column(Integer)
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    clusters: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    anomalies: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON)


class AiTestSuggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_test_suggestions"
    __table_args__ = (
        UniqueConstraint("suggestion_id", name="uq_ai_test_suggestions_suggestion_id"),
        UniqueConstraint("request_id", name="uq_ai_test_suggestions_request_id"),
    )

    suggestion_id: Mapped[str] = mapped_column(String(64), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_analysis_requests.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    requirement_refs: Mapped[list[str]] = mapped_column(JSON)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON)
    candidate: Mapped[dict[str, Any]] = mapped_column(JSON)
    rationale: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), index=True, default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_definition_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("test_definitions.id", ondelete="RESTRICT"), nullable=True
    )
    promoted_definition_external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
