"""Add deterministic drive-cycle range estimation."""

import sqlalchemy as sa
from alembic import op

revision = "0042_range_estimation"
down_revision = "0041_thermal_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "range_estimator_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_mass_kg", sa.Float(), nullable=False),
        sa.Column("drag_coefficient", sa.Float(), nullable=False),
        sa.Column("frontal_area_m2", sa.Float(), nullable=False),
        sa.Column("rolling_resistance_coefficient", sa.Float(), nullable=False),
        sa.Column("drivetrain_efficiency_pct", sa.Float(), nullable=False),
        sa.Column("regenerative_efficiency_pct", sa.Float(), nullable=False),
        sa.Column("base_auxiliary_power_kw", sa.Float(), nullable=False),
        sa.Column("reserve_soc_pct", sa.Float(), nullable=False),
        sa.Column("last_cycle_id", sa.String(64), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("traction_energy_kwh", sa.Float(), nullable=False),
        sa.Column("auxiliary_energy_kwh", sa.Float(), nullable=False),
        sa.Column("recovered_energy_kwh", sa.Float(), nullable=False),
        sa.Column("net_energy_kwh", sa.Float(), nullable=False),
        sa.Column("consumption_kwh_per_100km", sa.Float(), nullable=False),
        sa.Column("estimated_range_km", sa.Float(), nullable=False),
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
        sa.CheckConstraint("vehicle_mass_kg > 0", name="ck_range_estimator_mass"),
        sa.CheckConstraint(
            "reserve_soc_pct >= 0 AND reserve_soc_pct <= 30", name="ck_range_reserve"
        ),
        sa.CheckConstraint("version >= 1", name="ck_range_estimator_version"),
        sa.CheckConstraint(
            "operating_state IN ('ready', 'completed', 'limited')",
            name="ck_range_estimator_operating_state",
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", name="uq_range_estimator_vehicle"),
    )
    op.create_index(
        "ix_range_estimator_states_vehicle_id", "range_estimator_states", ["vehicle_id"]
    )
    op.create_index(
        "ix_range_estimator_states_operating_state", "range_estimator_states", ["operating_state"]
    )
    op.create_table(
        "range_estimation_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("cycle_id", sa.String(64), nullable=False),
        sa.Column("segments", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("previous_battery_version", sa.Integer(), nullable=False),
        sa.Column("previous_thermal_version", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("duration_ms >= 1", name="ck_range_step_duration"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", "command_id", name="uq_range_step_command"),
    )
    op.create_index(
        "ix_range_estimation_steps_vehicle_id", "range_estimation_steps", ["vehicle_id"]
    )
    op.create_index(
        "ix_range_estimation_steps_requested_by_user_id",
        "range_estimation_steps",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("range_estimation_steps")
    op.drop_table("range_estimator_states")
