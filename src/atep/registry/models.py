from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PlatformModule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_modules"

    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    version: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="registered", index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lease_duration_seconds: Mapped[int] = mapped_column(Integer, default=60)
    heartbeat_token_hash: Mapped[str | None] = mapped_column(String(64))
    capabilities: Mapped[list["ModuleCapability"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ModuleCapability.name",
    )


class ModuleCapability(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "module_capabilities"
    __table_args__ = (
        UniqueConstraint("module_id", "name", name="uq_module_capabilities_module_name"),
    )

    module_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_modules.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(500), default="")
    module: Mapped[PlatformModule] = relationship(back_populates="capabilities")
