from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EnvironmentProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "environment_profiles"
    __table_args__ = (UniqueConstraint("profile_id", name="uq_environment_profiles_profile_id"),)

    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(500), default="")
    vehicle_kind: Mapped[str] = mapped_column(String(24), index=True)
    property_source: Mapped[str] = mapped_column(String(24), index=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
