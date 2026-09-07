from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Float,
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
    environment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    traffic_controls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class AdasSensorConfiguration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "adas_sensor_configurations"
    __table_args__ = (
        UniqueConstraint("scene_id", "sensor_id", name="uq_adas_scene_sensor"),
        CheckConstraint("max_range_m > 0", name="ck_adas_sensor_range"),
        CheckConstraint(
            "horizontal_fov_deg > 0 AND horizontal_fov_deg <= 360", name="ck_adas_sensor_fov"
        ),
        CheckConstraint("latency_ms >= 0", name="ck_adas_sensor_latency"),
        CheckConstraint("position_noise_stddev_m >= 0", name="ck_adas_sensor_noise"),
    )

    scene_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("adas_world_scenes.id", ondelete="CASCADE"), index=True
    )
    sensor_id: Mapped[str] = mapped_column(String(64))
    sensor_type: Mapped[str] = mapped_column(String(16), index=True)
    mount_position: Mapped[dict[str, Any]] = mapped_column(JSON)
    yaw_deg: Mapped[float] = mapped_column(Float, default=0)
    max_range_m: Mapped[float] = mapped_column(Float)
    horizontal_fov_deg: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    position_noise_stddev_m: Mapped[float] = mapped_column(Float, default=0)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class AdasSensorObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "adas_sensor_observations"
    __table_args__ = (
        UniqueConstraint(
            "sensor_configuration_id", "observation_id", name="uq_adas_sensor_observation"
        ),
        CheckConstraint("scene_revision >= 1", name="ck_adas_observation_revision"),
        CheckConstraint("scene_simulation_time_ms >= 0", name="ck_adas_observation_scene_time"),
        CheckConstraint("observed_simulation_time_ms >= 0", name="ck_adas_observation_time"),
    )

    sensor_configuration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("adas_sensor_configurations.id", ondelete="CASCADE"),
        index=True,
    )
    observation_id: Mapped[str] = mapped_column(String(64))
    scene_revision: Mapped[int] = mapped_column(Integer)
    scene_simulation_time_ms: Mapped[int] = mapped_column(BigInteger)
    observed_simulation_time_ms: Mapped[int] = mapped_column(BigInteger)
    seed: Mapped[int] = mapped_column(Integer)
    detections: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class AdasPerceptionResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "adas_perception_results"
    __table_args__ = (
        UniqueConstraint("sensor_observation_id", "result_id", name="uq_adas_perception_result"),
        CheckConstraint("scene_revision >= 1", name="ck_adas_perception_revision"),
    )

    sensor_observation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("adas_sensor_observations.id", ondelete="CASCADE"),
        index=True,
    )
    result_id: Mapped[str] = mapped_column(String(64))
    scene_revision: Mapped[int] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String(120))
    model_version: Mapped[str] = mapped_column(String(64))
    predictions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    overall_score: Mapped[dict[str, Any]] = mapped_column(JSON)
    scores_by_target: Mapped[dict[str, Any]] = mapped_column(JSON)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class AdasPlanningEvaluation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "adas_planning_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "perception_result_id", "evaluation_id", name="uq_adas_planning_evaluation"
        ),
        CheckConstraint("scene_revision >= 1", name="ck_adas_planning_revision"),
    )

    perception_result_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("adas_perception_results.id", ondelete="CASCADE"),
        index=True,
    )
    evaluation_id: Mapped[str] = mapped_column(String(64))
    scene_revision: Mapped[int] = mapped_column(Integer)
    input_parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    maneuver: Mapped[str] = mapped_column(String(32), index=True)
    risk_metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    alerts: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
