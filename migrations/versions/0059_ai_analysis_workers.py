"""Add deterministic AI analysis worker executions."""

import sqlalchemy as sa
from alembic import op

revision = "0059_ai_analysis_workers"
down_revision = "0058_performance_stress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_analysis_requests",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "ai_analysis_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.String(64), nullable=False),
        sa.Column("execution_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("executed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("provider_kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("attempt BETWEEN 1 AND 3", name="ck_ai_analysis_execution_attempt"),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')", name="ck_ai_analysis_execution_status"
        ),
        sa.CheckConstraint(
            "provider_kind IN ('local', 'external')", name="ck_ai_analysis_provider_kind"
        ),
        sa.ForeignKeyConstraint(["executed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["request_id"], ["ai_analysis_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_id", name="uq_ai_analysis_executions_execution_id"),
        sa.UniqueConstraint("request_id", "attempt", name="uq_ai_analysis_execution_attempt"),
    )
    for column in ("execution_id", "request_id", "executed_by_user_id", "provider_id", "status"):
        op.create_index(f"ix_ai_analysis_executions_{column}", "ai_analysis_executions", [column])


def downgrade() -> None:
    op.drop_table("ai_analysis_executions")
    op.drop_column("ai_analysis_requests", "attempt_count")
