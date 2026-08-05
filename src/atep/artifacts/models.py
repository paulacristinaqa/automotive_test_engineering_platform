from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TestArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "test_artifacts"
    __table_args__ = (
        UniqueConstraint("test_run_id", "artifact_id", name="uq_test_artifacts_run_artifact_id"),
        UniqueConstraint("object_key", name="uq_test_artifacts_object_key"),
    )

    test_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="RESTRICT"), index=True
    )
    artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[str] = mapped_column(String(24), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    object_key: Mapped[str] = mapped_column(String(255))
