from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TestDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "test_definitions"
    __table_args__ = (
        UniqueConstraint("definition_id", name="uq_test_definitions_definition_id"),
    )

    definition_id: Mapped[str] = mapped_column(String(64), index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(32), index=True)
    level: Mapped[str] = mapped_column(String(24), index=True)
    automation_mode: Mapped[str] = mapped_column(String(16), index=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    preconditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TestSuite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "test_suites"
    __table_args__ = (UniqueConstraint("suite_id", name="uq_test_suites_suite_id"),)

    suite_id: Mapped[str] = mapped_column(String(64), index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    suite_type: Mapped[str] = mapped_column(String(20), index=True)
    composition: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
