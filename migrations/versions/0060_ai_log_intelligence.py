"""Add bounded deterministic AI log intelligence."""

import sqlalchemy as sa
from alembic import op

revision = "0060_ai_log_intelligence"
down_revision = "0059_ai_analysis_workers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_log_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("parsed_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("timeline", sa.JSON(), nullable=False),
        sa.Column("clusters", sa.JSON(), nullable=False),
        sa.Column("anomalies", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("line_count BETWEEN 1 AND 500", name="ck_ai_log_analysis_line_count"),
        sa.CheckConstraint(
            "parsed_count BETWEEN 1 AND line_count", name="ck_ai_log_analysis_parsed_count"
        ),
        sa.CheckConstraint(
            "rejected_count = line_count - parsed_count",
            name="ck_ai_log_analysis_rejected_count",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["request_id"], ["ai_analysis_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", name="uq_ai_log_analyses_analysis_id"),
        sa.UniqueConstraint("request_id", name="uq_ai_log_analyses_request_id"),
    )
    for column in ("analysis_id", "request_id", "created_by_user_id", "source"):
        op.create_index(f"ix_ai_log_analyses_{column}", "ai_log_analyses", [column])


def downgrade() -> None:
    op.drop_table("ai_log_analyses")
