"""Add deterministic UDS routine definitions and state."""

import sqlalchemy as sa
from alembic import op

revision = "0033_diagnostic_routines"
down_revision = "0032_diagnostic_data_identifiers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_routines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ecu_id", sa.Uuid(), nullable=False),
        sa.Column("identifier", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("allowed_sessions", sa.JSON(), nullable=False),
        sa.Column("execution_time_ms", sa.Integer(), nullable=False),
        sa.Column("supports_stop", sa.Boolean(), nullable=False),
        sa.Column("result_template", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "identifier >= 0 AND identifier <= 65535", name="ck_diagnostic_routine_identifier"
        ),
        sa.CheckConstraint(
            "execution_time_ms >= 0 AND execution_time_ms <= 600000",
            name="ck_diagnostic_routine_execution_time",
        ),
        sa.CheckConstraint("version >= 1", name="ck_diagnostic_routine_version"),
        sa.ForeignKeyConstraint(["ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecu_id", "identifier", name="uq_diagnostic_routine_identifier"),
    )
    op.create_index("ix_diagnostic_routines_ecu_id", "diagnostic_routines", ["ecu_id"])
    op.create_index("ix_diagnostic_routines_identifier", "diagnostic_routines", ["identifier"])
    op.create_index(
        "ix_diagnostic_routines_created_by_user_id",
        "diagnostic_routines",
        ["created_by_user_id"],
    )
    op.create_table(
        "diagnostic_routine_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("routine_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("invocation_count", sa.Integer(), nullable=False),
        sa.Column("started_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("completes_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("stopped_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("input_parameters", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('idle', 'running', 'completed', 'stopped')",
            name="ck_diagnostic_routine_state_status",
        ),
        sa.CheckConstraint("invocation_count >= 0", name="ck_diagnostic_routine_invocations"),
        sa.CheckConstraint("version >= 1", name="ck_diagnostic_routine_state_version"),
        sa.ForeignKeyConstraint(["routine_id"], ["diagnostic_routines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("routine_id", name="uq_diagnostic_routine_state"),
    )
    op.create_index(
        "ix_diagnostic_routine_states_routine_id",
        "diagnostic_routine_states",
        ["routine_id"],
    )
    op.create_index("ix_diagnostic_routine_states_status", "diagnostic_routine_states", ["status"])


def downgrade() -> None:
    op.drop_table("diagnostic_routine_states")
    op.drop_table("diagnostic_routines")
