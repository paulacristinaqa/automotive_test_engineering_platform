"""Add cross-platform ADAS integration evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0050_adas_integration_evidence"
down_revision = "0049_adas_test_scenarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adas_integration_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_execution_id", sa.Uuid(), nullable=False),
        sa.Column("test_run_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("telemetry_event_ids", sa.JSON(), nullable=False),
        sa.Column("vehicle_command_ids", sa.JSON(), nullable=False),
        sa.Column("carsystemui_evidence", sa.JSON(), nullable=False),
        sa.Column("dashboard_summary", sa.JSON(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["scenario_execution_id"],
            ["adas_test_scenario_executions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scenario_execution_id", name="uq_adas_integration_scenario"),
        sa.UniqueConstraint("evidence_id", name="uq_adas_integration_evidence_id"),
    )
    for column in ("scenario_execution_id", "test_run_id", "requested_by_user_id"):
        op.create_index(
            f"ix_adas_integration_evidence_{column}",
            "adas_integration_evidence",
            [column],
        )


def downgrade() -> None:
    op.drop_table("adas_integration_evidence")
