"""Add deterministic CAN arbitration execution evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0025_can_arbitration"
down_revision = "0024_can_network_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "can_arbitration_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("network_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("contender_count", sa.Integer(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("network_version", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["network_id"], ["can_networks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("network_id", "command_id", name="uq_can_arbitration_command"),
    )
    op.create_index(
        "ix_can_arbitration_executions_network_id",
        "can_arbitration_executions",
        ["network_id"],
    )
    op.create_index(
        "ix_can_arbitration_executions_requested_by_user_id",
        "can_arbitration_executions",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("can_arbitration_executions")
