"""Add DBC catalogue and deterministic signal codec evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0026_can_dbc_codec"
down_revision = "0025_can_arbitration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "can_dbc_catalogues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("network_id", sa.Uuid(), nullable=False),
        sa.Column("identifier", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("revision", sa.String(40), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("network_version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["network_id"], ["can_networks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("network_id"),
    )
    op.create_index("ix_can_dbc_catalogues_network_id", "can_dbc_catalogues", ["network_id"])
    op.create_index(
        "ix_can_dbc_catalogues_created_by_user_id",
        "can_dbc_catalogues",
        ["created_by_user_id"],
    )
    op.create_table(
        "can_signal_codec_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("network_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("contract_id", sa.String(80), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
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
        sa.UniqueConstraint("network_id", "command_id", name="uq_can_signal_codec_command"),
    )
    op.create_index(
        "ix_can_signal_codec_executions_network_id",
        "can_signal_codec_executions",
        ["network_id"],
    )
    op.create_index(
        "ix_can_signal_codec_executions_contract_id",
        "can_signal_codec_executions",
        ["contract_id"],
    )
    op.create_index(
        "ix_can_signal_codec_executions_requested_by_user_id",
        "can_signal_codec_executions",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("can_signal_codec_executions")
    op.drop_table("can_dbc_catalogues")
