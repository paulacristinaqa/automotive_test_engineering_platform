"""Add persisted ADAS perception results and ground-truth scores."""

import sqlalchemy as sa
from alembic import op

revision = "0047_adas_perception_scoring"
down_revision = "0046_adas_sensor_simulation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adas_perception_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sensor_observation_id", sa.Uuid(), nullable=False),
        sa.Column("result_id", sa.String(64), nullable=False),
        sa.Column("scene_revision", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("predictions", sa.JSON(), nullable=False),
        sa.Column("overall_score", sa.JSON(), nullable=False),
        sa.Column("scores_by_target", sa.JSON(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("scene_revision >= 1", name="ck_adas_perception_revision"),
        sa.ForeignKeyConstraint(
            ["sensor_observation_id"], ["adas_sensor_observations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sensor_observation_id", "result_id", name="uq_adas_perception_result"),
    )
    op.create_index(
        "ix_adas_perception_results_sensor_observation_id",
        "adas_perception_results",
        ["sensor_observation_id"],
    )
    op.create_index(
        "ix_adas_perception_results_requested_by_user_id",
        "adas_perception_results",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("adas_perception_results")
