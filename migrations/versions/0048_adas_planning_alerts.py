"""Add deterministic ADAS planning evaluations and alerts."""

import sqlalchemy as sa
from alembic import op

revision = "0048_adas_planning_alerts"
down_revision = "0047_adas_perception_scoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adas_planning_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("perception_result_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_id", sa.String(64), nullable=False),
        sa.Column("scene_revision", sa.Integer(), nullable=False),
        sa.Column("input_parameters", sa.JSON(), nullable=False),
        sa.Column("maneuver", sa.String(32), nullable=False),
        sa.Column("risk_metrics", sa.JSON(), nullable=False),
        sa.Column("alerts", sa.JSON(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("scene_revision >= 1", name="ck_adas_planning_revision"),
        sa.ForeignKeyConstraint(
            ["perception_result_id"], ["adas_perception_results.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "perception_result_id", "evaluation_id", name="uq_adas_planning_evaluation"
        ),
    )
    op.create_index(
        "ix_adas_planning_evaluations_perception_result_id",
        "adas_planning_evaluations",
        ["perception_result_id"],
    )
    op.create_index(
        "ix_adas_planning_evaluations_maneuver",
        "adas_planning_evaluations",
        ["maneuver"],
    )
    op.create_index(
        "ix_adas_planning_evaluations_requested_by_user_id",
        "adas_planning_evaluations",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("adas_planning_evaluations")
