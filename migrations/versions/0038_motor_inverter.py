"""Add deterministic motor and inverter simulation state."""

import sqlalchemy as sa
from alembic import op

revision = "0038_motor_inverter"
down_revision = "0037_battery_bms_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "motor_inverter_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("max_torque_nm", sa.Float(), nullable=False),
        sa.Column("max_speed_rpm", sa.Integer(), nullable=False),
        sa.Column("max_inverter_power_kw", sa.Float(), nullable=False),
        sa.Column("base_efficiency_pct", sa.Float(), nullable=False),
        sa.Column("requested_torque_nm", sa.Float(), nullable=False),
        sa.Column("delivered_torque_nm", sa.Float(), nullable=False),
        sa.Column("motor_speed_rpm", sa.Integer(), nullable=False),
        sa.Column("mechanical_power_kw", sa.Float(), nullable=False),
        sa.Column("electrical_power_kw", sa.Float(), nullable=False),
        sa.Column("efficiency_pct", sa.Float(), nullable=False),
        sa.Column("power_loss_kw", sa.Float(), nullable=False),
        sa.Column("motor_temperature_c", sa.Float(), nullable=False),
        sa.Column("inverter_temperature_c", sa.Float(), nullable=False),
        sa.Column("drive_mode", sa.String(16), nullable=False),
        sa.Column("operating_state", sa.String(16), nullable=False),
        sa.Column("limiting_reason", sa.String(32), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("max_torque_nm > 0", name="ck_motor_inverter_torque"),
        sa.CheckConstraint("max_speed_rpm > 0", name="ck_motor_inverter_speed"),
        sa.CheckConstraint("max_inverter_power_kw > 0", name="ck_motor_inverter_power"),
        sa.CheckConstraint(
            "base_efficiency_pct >= 50 AND base_efficiency_pct <= 100",
            name="ck_motor_inverter_efficiency",
        ),
        sa.CheckConstraint(
            "operating_state IN ('standby', 'ready', 'derated', 'protection')",
            name="ck_motor_inverter_operating_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_motor_inverter_version"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", name="uq_motor_inverter_vehicle"),
    )
    op.create_index("ix_motor_inverter_states_vehicle_id", "motor_inverter_states", ["vehicle_id"])
    op.create_index(
        "ix_motor_inverter_states_operating_state",
        "motor_inverter_states",
        ["operating_state"],
    )
    op.create_table(
        "motor_simulation_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("requested_torque_nm", sa.Float(), nullable=False),
        sa.Column("motor_speed_rpm", sa.Integer(), nullable=False),
        sa.Column("drive_mode", sa.String(16), nullable=False),
        sa.Column("ambient_temperature_c", sa.Float(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "duration_ms >= 1 AND duration_ms <= 3600000", name="ck_motor_step_duration"
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", "command_id", name="uq_motor_step_command"),
    )
    op.create_index(
        "ix_motor_simulation_steps_vehicle_id", "motor_simulation_steps", ["vehicle_id"]
    )
    op.create_index(
        "ix_motor_simulation_steps_requested_by_user_id",
        "motor_simulation_steps",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("motor_simulation_steps")
    op.drop_table("motor_inverter_states")
