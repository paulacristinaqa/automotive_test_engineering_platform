"""Add provider-neutral AI analysis requests."""

import sqlalchemy as sa
from alembic import op

revision = "0057_ai_analysis_foundation"
down_revision = "0056_cross_platform_automation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_analysis_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.String(32), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(80), nullable=False),
        sa.Column("provider_policy", sa.String(32), nullable=False),
        sa.Column("data_classification", sa.String(24), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_ai_analysis_requests_request_id"),
    )
    for column in (
        "request_id",
        "requested_by_user_id",
        "task",
        "subject_type",
        "subject_id",
        "provider_policy",
        "data_classification",
        "status",
    ):
        op.create_index(f"ix_ai_analysis_requests_{column}", "ai_analysis_requests", [column])


def downgrade() -> None:
    op.drop_table("ai_analysis_requests")
