"""Add deterministic ADAS world scenes."""

import sqlalchemy as sa
from alembic import op

revision = "0044_adas_world_model"
down_revision = "0043_electric_vehicle_scenarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adas_world_scenes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("coordinate_frame", sa.JSON(), nullable=False),
        sa.Column("roads", sa.JSON(), nullable=False),
        sa.Column("actors", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision >= 1", name="ck_adas_world_scene_revision"),
        sa.CheckConstraint("simulation_time_ms >= 0", name="ck_adas_world_scene_time"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", "scene_id", name="uq_adas_world_scene"),
    )
    op.create_index("ix_adas_world_scenes_vehicle_id", "adas_world_scenes", ["vehicle_id"])
    op.create_index(
        "ix_adas_world_scenes_created_by_user_id", "adas_world_scenes", ["created_by_user_id"]
    )


def downgrade() -> None:
    op.drop_table("adas_world_scenes")
