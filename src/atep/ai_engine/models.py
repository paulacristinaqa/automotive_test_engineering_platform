from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
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
