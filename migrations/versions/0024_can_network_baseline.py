"""Add the Volume IV CAN network baseline."""

import sqlalchemy as sa
from alembic import op

revision = "0024_can_network_baseline"
down_revision = "0023_ecu_scenarios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "can_networks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("identifier", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("bitrate_kbps", sa.Integer(), nullable=False),
        sa.Column("nodes", sa.JSON(), nullable=False),
        sa.Column("frame_contracts", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("simulation_time_us", sa.BigInteger(), nullable=False),
        sa.Column("next_sequence", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id"),
    )
    op.create_index("ix_can_networks_vehicle_id", "can_networks", ["vehicle_id"])
    op.create_table(
        "can_frame_transmissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("network_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("contract_id", sa.String(80), nullable=False),
        sa.Column("producer_node_id", sa.Uuid(), nullable=False),
        sa.Column("frame_id", sa.Integer(), nullable=False),
        sa.Column("frame_format", sa.String(20), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("transmission_time_us", sa.BigInteger(), nullable=False),
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
        sa.UniqueConstraint("network_id", "command_id", name="uq_can_frame_transmission_command"),
    )
    op.create_index(
        "ix_can_frame_transmissions_network_id", "can_frame_transmissions", ["network_id"]
    )
    op.create_index(
        "ix_can_frame_transmissions_contract_id", "can_frame_transmissions", ["contract_id"]
    )
    op.create_index(
        "ix_can_frame_transmissions_requested_by_user_id",
        "can_frame_transmissions",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("can_frame_transmissions")
    op.drop_table("can_networks")
