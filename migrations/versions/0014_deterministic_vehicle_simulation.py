"""Add deterministic vehicle simulation time and transition commands."""

import sqlalchemy as sa
from alembic import op

revision = "0014_vehicle_simulation"
down_revision = "0013_digital_vehicle_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vehicle_digital_states",
        sa.Column("simulation_time_ms", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.create_table(
        "vehicle_simulation_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("from_mode", sa.String(20), nullable=False),
        sa.Column("to_mode", sa.String(20), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("requested_speed_kph", sa.Float(), nullable=True),
        sa.Column("previous_state_version", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "vehicle_id", "command_id", name="uq_vehicle_simulation_transition_command"
        ),
    )
    op.create_index(
        "ix_vehicle_simulation_transitions_vehicle_id",
        "vehicle_simulation_transitions",
        ["vehicle_id"],
    )
    op.create_index(
        "ix_vehicle_simulation_transitions_requested_by_user_id",
        "vehicle_simulation_transitions",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vehicle_simulation_transitions_requested_by_user_id",
        table_name="vehicle_simulation_transitions",
    )
    op.drop_index(
        "ix_vehicle_simulation_transitions_vehicle_id",
        table_name="vehicle_simulation_transitions",
    )
    op.drop_table("vehicle_simulation_transitions")
    op.drop_column("vehicle_digital_states", "simulation_time_ms")
