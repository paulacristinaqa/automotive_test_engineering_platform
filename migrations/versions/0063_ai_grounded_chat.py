"""Add grounded internal chat conversations and bounded exchanges."""

import sqlalchemy as sa
from alembic import op

revision = "0063_ai_grounded_chat"
down_revision = "0062_ai_root_cause_risk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_chat_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("creation_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("retention_days BETWEEN 1 AND 30", name="ai_chat_retention"),
        sa.CheckConstraint("message_count BETWEEN 0 AND 50", name="ai_chat_message_count"),
        sa.CheckConstraint("status IN ('active', 'expired')", name="ai_chat_status"),
        sa.ForeignKeyConstraint(["request_id"], ["ai_analysis_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", name="uq_ai_chat_conversations_conversation_id"),
    )
    for column in ("conversation_id", "request_id", "owner_user_id", "expires_at", "status"):
        op.create_index(f"ix_ai_chat_conversations_{column}", "ai_chat_conversations", [column])

    op.create_table(
        "ai_chat_exchanges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exchange_id", sa.String(64), nullable=False),
        sa.Column("exchange_hash", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("sequence BETWEEN 1 AND 50", name="ai_chat_exchange_sequence"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["ai_chat_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exchange_id", name="uq_ai_chat_exchanges_exchange_id"),
        sa.UniqueConstraint(
            "conversation_id", "sequence", name="uq_ai_chat_exchanges_conversation_sequence"
        ),
    )
    for column in ("exchange_id", "conversation_id", "created_by_user_id"):
        op.create_index(f"ix_ai_chat_exchanges_{column}", "ai_chat_exchanges", [column])


def downgrade() -> None:
    op.drop_table("ai_chat_exchanges")
    op.drop_table("ai_chat_conversations")
