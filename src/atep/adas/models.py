from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AdasWorldScene(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "adas_world_scenes"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "scene_id", name="uq_adas_world_scene"),
        CheckConstraint("revision >= 1", name="ck_adas_world_scene_revision"),
        CheckConstraint("simulation_time_ms >= 0", name="ck_adas_world_scene_time"),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    coordinate_frame: Mapped[dict[str, Any]] = mapped_column(JSON)
    roads: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    actors: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
