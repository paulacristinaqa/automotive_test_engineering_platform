"""Bind catalog suites to runs and persist deterministic case results."""

import sqlalchemy as sa
from alembic import op

revision = "0052_test_execution_binding"
down_revision = "0051_test_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_runs", sa.Column("catalog_suite_id", sa.Uuid(), nullable=True))
    op.add_column("test_runs", sa.Column("catalog_suite_version", sa.Integer(), nullable=True))
    op.add_column("test_runs", sa.Column("catalog_suite_snapshot", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_test_runs_catalog_suite_id_test_suites",
        "test_runs",
        "test_suites",
        ["catalog_suite_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_test_runs_catalog_suite_id", "test_runs", ["catalog_suite_id"])

    op.create_table(
        "test_case_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_run_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("definition_id", sa.String(64), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("observed", sa.Text(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("test_run_id", "case_id", name="uq_test_case_results_run_case"),
    )
    for column in ("test_run_id", "definition_id", "status"):
        op.create_index(f"ix_test_case_results_{column}", "test_case_results", [column])


def downgrade() -> None:
    op.drop_table("test_case_results")
    op.drop_index("ix_test_runs_catalog_suite_id", table_name="test_runs")
    op.drop_constraint("fk_test_runs_catalog_suite_id_test_suites", "test_runs", type_="foreignkey")
    op.drop_column("test_runs", "catalog_suite_snapshot")
    op.drop_column("test_runs", "catalog_suite_version")
    op.drop_column("test_runs", "catalog_suite_id")
