"""Add bounded diagnostic campaigns and their execution evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0036_diagnostic_campaigns"
down_revision = "0035_diagnostic_flash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ecu_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("transport", sa.String(16), nullable=False),
        sa.Column("doip_envelope", sa.JSON(), nullable=True),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "transport IN ('local', 'doip')", name="ck_diagnostic_campaign_transport"
        ),
        sa.CheckConstraint("status IN ('completed')", name="ck_diagnostic_campaign_status"),
        sa.ForeignKeyConstraint(["ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecu_id", "command_id", name="uq_diagnostic_campaign_command"),
    )
    op.create_index("ix_diagnostic_campaigns_ecu_id", "diagnostic_campaigns", ["ecu_id"])
    op.create_index("ix_diagnostic_campaigns_transport", "diagnostic_campaigns", ["transport"])
    op.create_index("ix_diagnostic_campaigns_status", "diagnostic_campaigns", ["status"])
    op.create_index(
        "ix_diagnostic_campaigns_requested_by_user_id",
        "diagnostic_campaigns",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("diagnostic_campaigns")
