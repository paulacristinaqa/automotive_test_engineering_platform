"""Add persistent test-job scheduling and dispatch lifecycle."""

import sqlalchemy as sa
from alembic import op

revision = "0011_test_jobs"
down_revision = "0010_environment_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "test_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("environment_profile_id", sa.Uuid(), nullable=True),
        sa.Column("environment_profile_version", sa.Integer(), nullable=True),
        sa.Column("environment_snapshot", sa.JSON(), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("suite", sa.String(24), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("test_run_id", sa.Uuid(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["environment_profile_id"], ["environment_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_test_jobs_job_id"),
        sa.UniqueConstraint("run_id", name="uq_test_jobs_run_id"),
        sa.UniqueConstraint("test_run_id", name="uq_test_jobs_test_run_id"),
    )
    for column in (
        "job_id",
        "run_id",
        "vehicle_id",
        "requested_by_user_id",
        "environment_profile_id",
        "suite",
        "scheduled_for",
        "status",
    ):
        op.create_index(f"ix_test_jobs_{column}", "test_jobs", [column])


def downgrade() -> None:
    for column in (
        "status",
        "scheduled_for",
        "suite",
        "environment_profile_id",
        "requested_by_user_id",
        "vehicle_id",
        "run_id",
        "job_id",
    ):
        op.drop_index(f"ix_test_jobs_{column}", table_name="test_jobs")
    op.drop_table("test_jobs")
