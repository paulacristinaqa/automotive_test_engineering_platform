"""Add deterministic sensor and actuator simulation steps."""

import sqlalchemy as sa
from alembic import op

revision = "0015_vehicle_sensors"
down_revision = "0014_vehicle_simulation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vehicle_simulation_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("sensor_configuration", sa.JSON(), nullable=False),
        sa.Column("sensor_readings", sa.JSON(), nullable=False),
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
        sa.UniqueConstraint("vehicle_id", "command_id", name="uq_vehicle_simulation_step_command"),
    )
    op.create_index(
        "ix_vehicle_simulation_steps_vehicle_id", "vehicle_simulation_steps", ["vehicle_id"]
    )
    op.create_index(
        "ix_vehicle_simulation_steps_requested_by_user_id",
        "vehicle_simulation_steps",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vehicle_simulation_steps_requested_by_user_id", table_name="vehicle_simulation_steps"
    )
    op.drop_index("ix_vehicle_simulation_steps_vehicle_id", table_name="vehicle_simulation_steps")
    op.drop_table("vehicle_simulation_steps")
