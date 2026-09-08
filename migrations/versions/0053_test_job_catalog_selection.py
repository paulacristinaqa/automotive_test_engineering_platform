"""Add deterministic catalog selection to scheduled test jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0053_test_job_catalog_selection"
down_revision = "0052_test_execution_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_jobs", sa.Column("catalog_suite_id", sa.Uuid(), nullable=True))
    op.add_column("test_jobs", sa.Column("catalog_suite_version", sa.Integer(), nullable=True))
    op.add_column("test_jobs", sa.Column("selection_policy", sa.String(20), nullable=True))
    op.add_column("test_jobs", sa.Column("selection_snapshot", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_test_jobs_catalog_suite_id_test_suites",
        "test_jobs",
        "test_suites",
        ["catalog_suite_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_test_jobs_catalog_suite_id", "test_jobs", ["catalog_suite_id"])
    op.create_index("ix_test_jobs_selection_policy", "test_jobs", ["selection_policy"])


def downgrade() -> None:
    op.drop_index("ix_test_jobs_selection_policy", table_name="test_jobs")
    op.drop_index("ix_test_jobs_catalog_suite_id", table_name="test_jobs")
    op.drop_constraint("fk_test_jobs_catalog_suite_id_test_suites", "test_jobs", type_="foreignkey")
    op.drop_column("test_jobs", "selection_snapshot")
    op.drop_column("test_jobs", "selection_policy")
    op.drop_column("test_jobs", "catalog_suite_version")
    op.drop_column("test_jobs", "catalog_suite_id")
