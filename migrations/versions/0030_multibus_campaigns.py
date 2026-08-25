"""Add deterministic multi-bus campaign evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0030_multibus_campaigns"
down_revision = "0029_multibus_gateway"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "multibus_campaign_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("network_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("request_summary", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("network_version", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["network_id"], ["can_networks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("network_id", "command_id", name="uq_multibus_campaign_command"),
    )
    op.create_index(
        "ix_multibus_campaign_executions_network_id", "multibus_campaign_executions", ["network_id"]
    )
    op.create_index(
        "ix_multibus_campaign_executions_status", "multibus_campaign_executions", ["status"]
    )
    op.create_index(
        "ix_multibus_campaign_executions_requested_by_user_id",
        "multibus_campaign_executions",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("multibus_campaign_executions")
