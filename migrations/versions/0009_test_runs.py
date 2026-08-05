"""Add persistent test runs with optimistic state transitions."""

import sqlalchemy as sa
from alembic import op

revision = "0009_test_runs"
down_revision = "0008_vehicle_command_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "test_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("suite", sa.String(24), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_test_runs_run_id"),
    )
    for column in ("run_id", "vehicle_id", "requested_by_user_id", "suite", "status"):
        op.create_index(f"ix_test_runs_{column}", "test_runs", [column])


def downgrade() -> None:
    for column in ("status", "suite", "requested_by_user_id", "vehicle_id", "run_id"):
        op.drop_index(f"ix_test_runs_{column}", table_name="test_runs")
    op.drop_table("test_runs")
