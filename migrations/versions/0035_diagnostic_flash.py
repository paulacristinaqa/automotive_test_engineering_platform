"""Add bounded UDS firmware-transfer state."""

import sqlalchemy as sa
from alembic import op

revision = "0035_diagnostic_flash"
down_revision = "0034_diagnostic_security_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_flash_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ecu_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("memory_address", sa.Integer(), nullable=False),
        sa.Column("memory_size", sa.Integer(), nullable=False),
        sa.Column("firmware_version", sa.String(20), nullable=False),
        sa.Column("target_ecu_version", sa.Integer(), nullable=False),
        sa.Column("max_block_length", sa.Integer(), nullable=False),
        sa.Column("next_block_sequence_counter", sa.Integer(), nullable=False),
        sa.Column("bytes_received", sa.Integer(), nullable=False),
        sa.Column("image_data", sa.LargeBinary(), nullable=False),
        sa.Column("image_sha256", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('idle', 'downloading', 'completed')",
            name="ck_diagnostic_flash_status",
        ),
        sa.CheckConstraint("memory_address >= 0", name="ck_diagnostic_flash_address"),
        sa.CheckConstraint(
            "memory_size >= 0 AND memory_size <= 65536",
            name="ck_diagnostic_flash_size",
        ),
        sa.CheckConstraint(
            "bytes_received >= 0 AND bytes_received <= memory_size",
            name="ck_diagnostic_flash_received",
        ),
        sa.CheckConstraint(
            "next_block_sequence_counter >= 0 AND next_block_sequence_counter <= 255",
            name="ck_diagnostic_flash_sequence",
        ),
        sa.CheckConstraint("version >= 1", name="ck_diagnostic_flash_version"),
        sa.ForeignKeyConstraint(["ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecu_id", name="uq_diagnostic_flash_ecu"),
    )
    op.create_index("ix_diagnostic_flash_states_ecu_id", "diagnostic_flash_states", ["ecu_id"])
    op.create_index("ix_diagnostic_flash_states_status", "diagnostic_flash_states", ["status"])


def downgrade() -> None:
    op.drop_table("diagnostic_flash_states")
