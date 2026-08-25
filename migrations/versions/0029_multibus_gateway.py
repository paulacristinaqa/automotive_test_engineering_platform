"""Add LIN, Ethernet, and deterministic gateway routing."""

import sqlalchemy as sa
from alembic import op

revision = "0029_multibus_gateway"
down_revision = "0028_can_faults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("lin_channels", "ethernet_segments", "gateway_routes"):
        op.add_column(
            "can_networks",
            sa.Column(name, sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        )
    op.create_table(
        "multibus_gateway_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("network_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("route_id", sa.String(80), nullable=True),
        sa.Column("request", sa.JSON(), nullable=False),
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
        sa.UniqueConstraint("network_id", "command_id", name="uq_multibus_gateway_command"),
    )
    op.create_index(
        "ix_multibus_gateway_executions_network_id",
        "multibus_gateway_executions",
        ["network_id"],
    )
    op.create_index(
        "ix_multibus_gateway_executions_route_id",
        "multibus_gateway_executions",
        ["route_id"],
    )
    op.create_index(
        "ix_multibus_gateway_executions_requested_by_user_id",
        "multibus_gateway_executions",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("multibus_gateway_executions")
    op.drop_column("can_networks", "gateway_routes")
    op.drop_column("can_networks", "ethernet_segments")
    op.drop_column("can_networks", "lin_channels")
