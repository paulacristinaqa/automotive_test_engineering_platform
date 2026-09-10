"""Add cross-platform AI evidence projections."""

import sqlalchemy as sa
from alembic import op

revision = "0064_ai_evidence_projections"
down_revision = "0063_ai_grounded_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_evidence_projections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("projection_id", sa.String(64), nullable=False),
        sa.Column("projection_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("consumer", sa.String(24), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("headline", sa.String(160), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("contract_version", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "consumer IN ('carsystemui', 'dashboard')", name="ai_projection_consumer"
        ),
        sa.CheckConstraint(
            "source_type IN ('analysis_execution', 'log_analysis', 'test_suggestion', "
            "'root_cause_risk', 'chat_exchange')",
            name="ai_projection_source_type",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="ai_projection_severity",
        ),
        sa.ForeignKeyConstraint(["request_id"], ["ai_analysis_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("projection_id", name="uq_ai_evidence_projections_projection_id"),
    )
    for column in (
        "projection_id",
        "request_id",
        "created_by_user_id",
        "consumer",
        "source_type",
        "source_id",
        "subject_type",
        "subject_id",
        "status",
        "severity",
    ):
        op.create_index(f"ix_ai_evidence_projections_{column}", "ai_evidence_projections", [column])


def downgrade() -> None:
    op.drop_table("ai_evidence_projections")
