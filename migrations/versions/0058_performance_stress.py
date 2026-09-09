"""Add bounded performance profiles and comparable executions."""

import sqlalchemy as sa
from alembic import op

revision = "0058_performance_stress"
down_revision = "0057_ai_analysis_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performance_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("workload_type", sa.String(16), nullable=False),
        sa.Column("target", sa.String(200), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.Column("resource_limits", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", name="uq_performance_profiles_profile_id"),
    )
    op.create_table(
        "performance_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("test_run_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_execution_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("threshold_results", sa.JSON(), nullable=False),
        sa.Column("comparison", sa.JSON(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["performance_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["baseline_execution_id"], ["performance_executions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_id", name="uq_performance_executions_execution_id"),
    )
    for table, columns in (
        ("performance_profiles", ("profile_id", "created_by_user_id", "workload_type")),
        (
            "performance_executions",
            (
                "execution_id",
                "profile_id",
                "test_run_id",
                "baseline_execution_id",
                "recorded_by_user_id",
                "outcome",
            ),
        ),
    ):
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    op.drop_table("performance_executions")
    op.drop_table("performance_profiles")
