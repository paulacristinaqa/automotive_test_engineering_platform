"""Add governed AI test suggestions and review evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0061_ai_test_suggestions"
down_revision = "0060_ai_log_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_test_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("suggestion_id", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_refs", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("candidate", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_definition_id", sa.Uuid(), nullable=True),
        sa.Column("promoted_definition_external_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version >= 1", name="ck_ai_test_suggestions_version"),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'rejected', 'promoted')",
            name="ck_ai_test_suggestions_status",
        ),
        sa.ForeignKeyConstraint(["request_id"], ["ai_analysis_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["promoted_definition_id"], ["test_definitions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("suggestion_id", name="uq_ai_test_suggestions_suggestion_id"),
        sa.UniqueConstraint("request_id", name="uq_ai_test_suggestions_request_id"),
    )
    for column in ("suggestion_id", "request_id", "created_by_user_id", "status"):
        op.create_index(f"ix_ai_test_suggestions_{column}", "ai_test_suggestions", [column])


def downgrade() -> None:
    op.drop_table("ai_test_suggestions")
