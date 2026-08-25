"""Add UDS diagnostic sessions, commands, and DTC storage."""

import sqlalchemy as sa
from alembic import op

revision = "0031_diagnostics_foundation"
down_revision = "0030_multibus_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_session_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ecu_id", sa.Uuid(), nullable=False),
        sa.Column("session_type", sa.String(24), nullable=False),
        sa.Column("security_level", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecu_id", name="uq_diagnostic_session_ecu"),
    )
    op.create_index("ix_diagnostic_session_states_ecu_id", "diagnostic_session_states", ["ecu_id"])
    op.create_index(
        "ix_diagnostic_session_states_session_type", "diagnostic_session_states", ["session_type"]
    )
    op.create_table(
        "diagnostic_commands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ecu_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecu_id", "command_id", name="uq_diagnostic_command"),
    )
    op.create_index("ix_diagnostic_commands_ecu_id", "diagnostic_commands", ["ecu_id"])
    op.create_index("ix_diagnostic_commands_service_id", "diagnostic_commands", ["service_id"])
    op.create_index(
        "ix_diagnostic_commands_requested_by_user_id",
        "diagnostic_commands",
        ["requested_by_user_id"],
    )
    op.create_table(
        "diagnostic_trouble_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ecu_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("status_mask", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_ms", sa.BigInteger(), nullable=False),
        sa.Column("last_seen_ms", sa.BigInteger(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecu_id", "code", name="uq_diagnostic_trouble_code"),
    )
    op.create_index("ix_diagnostic_trouble_codes_ecu_id", "diagnostic_trouble_codes", ["ecu_id"])
    op.create_index("ix_diagnostic_trouble_codes_code", "diagnostic_trouble_codes", ["code"])
    op.create_index(
        "ix_diagnostic_trouble_codes_status_mask", "diagnostic_trouble_codes", ["status_mask"]
    )
    op.create_index(
        "ix_diagnostic_trouble_codes_severity", "diagnostic_trouble_codes", ["severity"]
    )


def downgrade() -> None:
    op.drop_table("diagnostic_trouble_codes")
    op.drop_table("diagnostic_commands")
    op.drop_table("diagnostic_session_states")
