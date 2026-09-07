"""Add deterministic ADAS sensor configurations and observations."""

import sqlalchemy as sa
from alembic import op

revision = "0046_adas_sensor_simulation"
down_revision = "0045_adas_environment_traffic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adas_sensor_configurations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.Uuid(), nullable=False),
        sa.Column("sensor_id", sa.String(64), nullable=False),
        sa.Column("sensor_type", sa.String(16), nullable=False),
        sa.Column("mount_position", sa.JSON(), nullable=False),
        sa.Column("yaw_deg", sa.Float(), nullable=False),
        sa.Column("max_range_m", sa.Float(), nullable=False),
        sa.Column("horizontal_fov_deg", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("position_noise_stddev_m", sa.Float(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("max_range_m > 0", name="ck_adas_sensor_range"),
        sa.CheckConstraint(
            "horizontal_fov_deg > 0 AND horizontal_fov_deg <= 360", name="ck_adas_sensor_fov"
        ),
        sa.CheckConstraint("latency_ms >= 0", name="ck_adas_sensor_latency"),
        sa.CheckConstraint("position_noise_stddev_m >= 0", name="ck_adas_sensor_noise"),
        sa.ForeignKeyConstraint(["scene_id"], ["adas_world_scenes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scene_id", "sensor_id", name="uq_adas_scene_sensor"),
    )
    op.create_index(
        "ix_adas_sensor_configurations_scene_id", "adas_sensor_configurations", ["scene_id"]
    )
    op.create_index(
        "ix_adas_sensor_configurations_sensor_type", "adas_sensor_configurations", ["sensor_type"]
    )
    op.create_index(
        "ix_adas_sensor_configurations_created_by_user_id",
        "adas_sensor_configurations",
        ["created_by_user_id"],
    )
    op.create_table(
        "adas_sensor_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sensor_configuration_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.String(64), nullable=False),
        sa.Column("scene_revision", sa.Integer(), nullable=False),
        sa.Column("scene_simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("observed_simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("detections", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("scene_revision >= 1", name="ck_adas_observation_revision"),
        sa.CheckConstraint("scene_simulation_time_ms >= 0", name="ck_adas_observation_scene_time"),
        sa.CheckConstraint("observed_simulation_time_ms >= 0", name="ck_adas_observation_time"),
        sa.ForeignKeyConstraint(
            ["sensor_configuration_id"], ["adas_sensor_configurations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sensor_configuration_id", "observation_id", name="uq_adas_sensor_observation"
        ),
    )
    op.create_index(
        "ix_adas_sensor_observations_sensor_configuration_id",
        "adas_sensor_observations",
        ["sensor_configuration_id"],
    )
    op.create_index(
        "ix_adas_sensor_observations_requested_by_user_id",
        "adas_sensor_observations",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("adas_sensor_observations")
    op.drop_table("adas_sensor_configurations")
