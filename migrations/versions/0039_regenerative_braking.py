"""Add regenerative and blended braking simulation state."""

import sqlalchemy as sa
from alembic import op

revision = "0039_regenerative_braking"
down_revision = "0038_motor_inverter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regenerative_brake_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_mass_kg", sa.Float(), nullable=False),
        sa.Column("wheel_radius_m", sa.Float(), nullable=False),
        sa.Column("final_drive_ratio", sa.Float(), nullable=False),
        sa.Column("drivetrain_efficiency_pct", sa.Float(), nullable=False),
        sa.Column("max_regen_torque_nm", sa.Float(), nullable=False),
        sa.Column("max_regen_power_kw", sa.Float(), nullable=False),
        sa.Column("regen_efficiency_pct", sa.Float(), nullable=False),
        sa.Column("max_friction_deceleration_mps2", sa.Float(), nullable=False),
        sa.Column("requested_deceleration_mps2", sa.Float(), nullable=False),
        sa.Column("delivered_deceleration_mps2", sa.Float(), nullable=False),
        sa.Column("vehicle_speed_mps", sa.Float(), nullable=False),
        sa.Column("regenerative_deceleration_mps2", sa.Float(), nullable=False),
        sa.Column("friction_deceleration_mps2", sa.Float(), nullable=False),
        sa.Column("regenerative_motor_torque_nm", sa.Float(), nullable=False),
        sa.Column("recovered_power_kw", sa.Float(), nullable=False),
        sa.Column("recovered_energy_kwh", sa.Float(), nullable=False),
        sa.Column("cumulative_recovered_energy_kwh", sa.Float(), nullable=False),
        sa.Column("battery_charge_acceptance_kw", sa.Float(), nullable=False),
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
        sa.CheckConstraint("vehicle_mass_kg > 0", name="ck_regenerative_brake_mass"),
        sa.CheckConstraint("wheel_radius_m > 0", name="ck_regenerative_brake_wheel_radius"),
        sa.CheckConstraint("final_drive_ratio > 0", name="ck_regenerative_brake_drive_ratio"),
        sa.CheckConstraint(
            "drivetrain_efficiency_pct > 0 AND drivetrain_efficiency_pct <= 100",
            name="ck_regenerative_brake_drivetrain_efficiency",
        ),
        sa.CheckConstraint("max_regen_torque_nm > 0", name="ck_regenerative_brake_torque"),
        sa.CheckConstraint("max_regen_power_kw > 0", name="ck_regenerative_brake_power"),
        sa.CheckConstraint(
            "regen_efficiency_pct > 0 AND regen_efficiency_pct <= 100",
            name="ck_regenerative_brake_efficiency",
        ),
        sa.CheckConstraint(
            "max_friction_deceleration_mps2 > 0",
            name="ck_regenerative_brake_friction",
        ),
        sa.CheckConstraint("version >= 1", name="ck_regenerative_brake_version"),
        sa.CheckConstraint(
            "operating_state IN ('standby', 'regenerative', 'blended', 'friction', 'limited')",
            name="ck_regenerative_brake_operating_state",
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", name="uq_regenerative_brake_vehicle"),
    )
    op.create_index(
        "ix_regenerative_brake_states_vehicle_id",
        "regenerative_brake_states",
        ["vehicle_id"],
    )
    op.create_index(
        "ix_regenerative_brake_states_operating_state",
        "regenerative_brake_states",
        ["operating_state"],
    )
    op.create_table(
        "brake_simulation_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("requested_deceleration_mps2", sa.Float(), nullable=False),
        sa.Column("vehicle_speed_mps", sa.Float(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("previous_battery_version", sa.Integer(), nullable=False),
        sa.Column("battery_state_version", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "duration_ms >= 1 AND duration_ms <= 3600000", name="ck_brake_step_duration"
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", "command_id", name="uq_brake_step_command"),
    )
    op.create_index(
        "ix_brake_simulation_steps_vehicle_id", "brake_simulation_steps", ["vehicle_id"]
    )
    op.create_index(
        "ix_brake_simulation_steps_requested_by_user_id",
        "brake_simulation_steps",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("brake_simulation_steps")
    op.drop_table("regenerative_brake_states")
