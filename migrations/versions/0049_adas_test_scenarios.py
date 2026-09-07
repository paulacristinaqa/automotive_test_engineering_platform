"""Add deterministic ADAS test scenario executions."""

import sqlalchemy as sa
from alembic import op

revision = "0049_adas_test_scenarios"
down_revision = "0048_adas_planning_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adas_test_scenario_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.Uuid(), nullable=False),
        sa.Column("perception_result_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.String(64), nullable=False),
        sa.Column("scenario_type", sa.String(40), nullable=False),
        sa.Column("scene_revision", sa.Integer(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("maneuver", sa.String(32), nullable=False),
        sa.Column("alerts", sa.JSON(), nullable=False),
        sa.Column("assertions", sa.JSON(), nullable=False),
        sa.Column("fault_injections", sa.JSON(), nullable=False),
        sa.Column("coverage", sa.JSON(), nullable=False),
        sa.Column("regression_fingerprint", sa.String(64), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("scene_revision >= 1", name="ck_adas_scenario_revision"),
        sa.ForeignKeyConstraint(["scene_id"], ["adas_world_scenes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["perception_result_id"], ["adas_perception_results.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scene_id", "execution_id", name="uq_adas_test_scenario_execution"),
    )
    for column in (
        "scene_id",
        "perception_result_id",
        "scenario_type",
        "status",
        "regression_fingerprint",
        "requested_by_user_id",
    ):
        op.create_index(
            f"ix_adas_test_scenario_executions_{column}",
            "adas_test_scenario_executions",
            [column],
        )


def downgrade() -> None:
    op.drop_table("adas_test_scenario_executions")
