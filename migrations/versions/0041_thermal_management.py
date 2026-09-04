"""Add active thermal-management state and deterministic steps."""

import sqlalchemy as sa
from alembic import op

revision = "0041_thermal_management"
down_revision = "0040_charging_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thermal_management_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("max_battery_thermal_power_kw", sa.Float(), nullable=False),
        sa.Column("max_powertrain_thermal_power_kw", sa.Float(), nullable=False),
        sa.Column("max_cabin_thermal_power_kw", sa.Float(), nullable=False),
        sa.Column("battery_target_temperature_c", sa.Float(), nullable=False),
        sa.Column("motor_target_temperature_c", sa.Float(), nullable=False),
        sa.Column("inverter_target_temperature_c", sa.Float(), nullable=False),
        sa.Column("cabin_target_temperature_c", sa.Float(), nullable=False),
        sa.Column("cabin_temperature_c", sa.Float(), nullable=False),
        sa.Column("battery_thermal_power_kw", sa.Float(), nullable=False),
        sa.Column("motor_thermal_power_kw", sa.Float(), nullable=False),
        sa.Column("inverter_thermal_power_kw", sa.Float(), nullable=False),
        sa.Column("cabin_thermal_power_kw", sa.Float(), nullable=False),
        sa.Column("auxiliary_power_kw", sa.Float(), nullable=False),
        sa.Column("operating_state", sa.String(16), nullable=False),
        sa.Column("limiting_reason", sa.String(32), nullable=True),
        sa.Column("fault_code", sa.String(32), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("max_battery_thermal_power_kw > 0", name="ck_thermal_battery_power"),
        sa.CheckConstraint(
            "max_powertrain_thermal_power_kw > 0", name="ck_thermal_powertrain_power"
        ),
        sa.CheckConstraint("max_cabin_thermal_power_kw > 0", name="ck_thermal_cabin_power"),
        sa.CheckConstraint("version >= 1", name="ck_thermal_management_version"),
        sa.CheckConstraint(
            "operating_state IN ('standby', 'heating', 'cooling', 'mixed', 'faulted')",
            name="ck_thermal_management_operating_state",
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", name="uq_thermal_management_vehicle"),
    )
    op.create_index(
        "ix_thermal_management_states_vehicle_id", "thermal_management_states", ["vehicle_id"]
    )
    op.create_index(
        "ix_thermal_management_states_operating_state",
        "thermal_management_states",
        ["operating_state"],
    )
    op.create_table(
        "thermal_management_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("ambient_temperature_c", sa.Float(), nullable=False),
        sa.Column("cabin_heat_load_kw", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("fault_code", sa.String(32), nullable=True),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("previous_battery_version", sa.Integer(), nullable=False),
        sa.Column("battery_state_version", sa.Integer(), nullable=False),
        sa.Column("previous_motor_version", sa.Integer(), nullable=False),
        sa.Column("motor_state_version", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "duration_ms >= 1 AND duration_ms <= 3600000", name="ck_thermal_step_duration"
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", "command_id", name="uq_thermal_step_command"),
    )
    op.create_index(
        "ix_thermal_management_steps_vehicle_id", "thermal_management_steps", ["vehicle_id"]
    )
    op.create_index(
        "ix_thermal_management_steps_requested_by_user_id",
        "thermal_management_steps",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("thermal_management_steps")
    op.drop_table("thermal_management_states")
