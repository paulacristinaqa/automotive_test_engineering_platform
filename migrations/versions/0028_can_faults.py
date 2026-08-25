"""Add deterministic CAN fault executions and node error states."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_can_faults"
down_revision = "0027_can_fd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "can_networks",
        sa.Column("error_states", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.create_table(
        "can_fault_executions",
        sa.Column("network_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("network_version", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["network_id"], ["can_networks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("network_id", "command_id", name="uq_can_fault_command"),
    )
    op.create_index("ix_can_fault_executions_network_id", "can_fault_executions", ["network_id"])
    op.create_index(
        "ix_can_fault_executions_target_node_id", "can_fault_executions", ["target_node_id"]
    )
    op.create_index(
        "ix_can_fault_executions_requested_by_user_id",
        "can_fault_executions",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("can_fault_executions")
    op.drop_column("can_networks", "error_states")
