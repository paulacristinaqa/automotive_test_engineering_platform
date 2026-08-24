"""Add ECU memory regions and bounded snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0021_ecu_memory_regions"
down_revision = "0020_ecu_behavior_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "electronic_control_units",
        sa.Column("memory_regions", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "ecu_memory_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ecu_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("memory", sa.JSON(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ecu_memory_snapshots_ecu_id", "ecu_memory_snapshots", ["ecu_id"])
    op.create_index(
        "ix_ecu_memory_snapshots_created_by_user_id",
        "ecu_memory_snapshots",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("ecu_memory_snapshots")
    op.drop_column("electronic_control_units", "memory_regions")
