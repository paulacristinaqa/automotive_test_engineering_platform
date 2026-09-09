"""Add mutation campaigns, results, and requirement coverage."""

import sqlalchemy as sa
from alembic import op

revision = "0055_mutation_analysis"
down_revision = "0054_fault_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mutation_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_suite_id", sa.Uuid(), nullable=False),
        sa.Column("suite_version", sa.Integer(), nullable=False),
        sa.Column("suite_snapshot", sa.JSON(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("mutants", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["catalog_suite_id"], ["test_suites.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="uq_mutation_campaigns_campaign_id"),
    )
    for column in ("campaign_id", "created_by_user_id", "catalog_suite_id", "status"):
        op.create_index(f"ix_mutation_campaigns_{column}", "mutation_campaigns", [column])

    op.create_table(
        "mutation_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.String(64), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_version", sa.Integer(), nullable=False),
        sa.Column("campaign_snapshot", sa.JSON(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("test_run_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("total_mutants", sa.Integer(), nullable=False),
        sa.Column("completed_mutants", sa.Integer(), nullable=False),
        sa.Column("killed_mutants", sa.Integer(), nullable=False),
        sa.Column("survived_mutants", sa.Integer(), nullable=False),
        sa.Column("mutation_score", sa.Float(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["mutation_campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_id", name="uq_mutation_executions_execution_id"),
    )
    for column in (
        "execution_id",
        "campaign_id",
        "vehicle_id",
        "test_run_id",
        "requested_by_user_id",
        "status",
    ):
        op.create_index(f"ix_mutation_executions_{column}", "mutation_executions", [column])

    op.create_table(
        "mutant_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("mutant_id", sa.String(64), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("operator", sa.String(32), nullable=False),
        sa.Column("target", sa.String(240), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("detected_by", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["execution_id"], ["mutation_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_id", "mutant_id", name="uq_mutant_results_execution_mutant"),
    )
    for column in ("execution_id", "operator", "status"):
        op.create_index(f"ix_mutant_results_{column}", "mutant_results", [column])

    op.create_table(
        "requirement_coverage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.String(80), nullable=False),
        sa.Column("managed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("criticality", sa.String(16), nullable=False),
        sa.Column("definition_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["managed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("requirement_id", name="uq_requirement_coverage_requirement_id"),
    )
    for column in ("requirement_id", "managed_by_user_id", "criticality", "status"):
        op.create_index(f"ix_requirement_coverage_{column}", "requirement_coverage", [column])


def downgrade() -> None:
    op.drop_table("requirement_coverage")
    op.drop_table("mutant_results")
    op.drop_table("mutation_executions")
    op.drop_table("mutation_campaigns")
