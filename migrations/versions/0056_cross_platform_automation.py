"""Add cross-platform automation reports."""

import sqlalchemy as sa
from alembic import op

revision = "0056_cross_platform_automation"
down_revision = "0055_mutation_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cross_platform_automation_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("test_run_id", sa.Uuid(), nullable=False),
        sa.Column("gateway_module_id", sa.Uuid(), nullable=False),
        sa.Column("fault_execution_id", sa.Uuid(), nullable=True),
        sa.Column("mutation_execution_id", sa.Uuid(), nullable=True),
        sa.Column("telemetry_event_ids", sa.JSON(), nullable=False),
        sa.Column("vehicle_command_ids", sa.JSON(), nullable=False),
        sa.Column("carsystemui_observations", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["gateway_module_id"], ["platform_modules.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["fault_execution_id"], ["fault_campaign_executions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["mutation_execution_id"], ["mutation_executions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id", name="uq_cross_platform_automation_report_id"),
        sa.UniqueConstraint("test_run_id", name="uq_cross_platform_automation_test_run"),
    )
    for column in (
        "report_id",
        "vehicle_id",
        "test_run_id",
        "gateway_module_id",
        "fault_execution_id",
        "mutation_execution_id",
        "outcome",
        "created_by_user_id",
    ):
        op.create_index(
            f"ix_cross_platform_automation_reports_{column}",
            "cross_platform_automation_reports",
            [column],
        )


def downgrade() -> None:
    op.drop_table("cross_platform_automation_reports")
