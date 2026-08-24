"""Add deterministic ECU execution clock, task configuration, and command evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0019_ecu_execution_clock"
down_revision = "0018_ecu_aggregate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "electronic_control_units",
        sa.Column("cyclic_tasks", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "electronic_control_units",
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "electronic_control_units",
        sa.Column("boot_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "ecu_simulation_commands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ecu_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("previous_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecu_id", "command_id", name="uq_ecu_sim_command"),
    )
    op.create_index("ix_ecu_simulation_commands_ecu_id", "ecu_simulation_commands", ["ecu_id"])
    op.create_index("ix_ecu_simulation_commands_kind", "ecu_simulation_commands", ["kind"])
    op.create_index(
        "ix_ecu_simulation_commands_requested_by_user_id",
        "ecu_simulation_commands",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("ecu_simulation_commands")
    op.drop_column("electronic_control_units", "boot_count")
    op.drop_column("electronic_control_units", "simulation_time_ms")
    op.drop_column("electronic_control_units", "cyclic_tasks")
