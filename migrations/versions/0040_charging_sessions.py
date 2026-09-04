"""Add deterministic AC and DC charging session state."""

import sqlalchemy as sa
from alembic import op

revision = "0040_charging_sessions"
down_revision = "0039_regenerative_braking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "charging_system_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("max_ac_power_kw", sa.Float(), nullable=False),
        sa.Column("max_dc_power_kw", sa.Float(), nullable=False),
        sa.Column("charging_efficiency_pct", sa.Float(), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("connector_type", sa.String(16), nullable=True),
        sa.Column("target_soc_pct", sa.Float(), nullable=False),
        sa.Column("requested_power_kw", sa.Float(), nullable=False),
        sa.Column("delivered_power_kw", sa.Float(), nullable=False),
        sa.Column("charged_energy_kwh", sa.Float(), nullable=False),
        sa.Column("session_energy_kwh", sa.Float(), nullable=False),
        sa.Column("battery_charge_acceptance_kw", sa.Float(), nullable=False),
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
        sa.CheckConstraint("max_ac_power_kw > 0", name="ck_charging_system_ac_power"),
        sa.CheckConstraint("max_dc_power_kw > 0", name="ck_charging_system_dc_power"),
        sa.CheckConstraint(
            "charging_efficiency_pct > 0 AND charging_efficiency_pct <= 100",
            name="ck_charging_system_efficiency",
        ),
        sa.CheckConstraint(
            "target_soc_pct >= 1 AND target_soc_pct <= 100", name="ck_charging_target_soc"
        ),
        sa.CheckConstraint("version >= 1", name="ck_charging_system_version"),
        sa.CheckConstraint(
            "operating_state IN ('idle', 'charging', 'paused', 'completed', 'faulted')",
            name="ck_charging_system_operating_state",
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", name="uq_charging_system_vehicle"),
    )
    op.create_index(
        "ix_charging_system_states_vehicle_id", "charging_system_states", ["vehicle_id"]
    )
    op.create_index(
        "ix_charging_system_states_operating_state",
        "charging_system_states",
        ["operating_state"],
    )
    op.create_table(
        "charging_command_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("connector_type", sa.String(16), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("requested_power_kw", sa.Float(), nullable=False),
        sa.Column("target_soc_pct", sa.Float(), nullable=True),
        sa.Column("fault_code", sa.String(32), nullable=True),
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
            "duration_ms >= 0 AND duration_ms <= 3600000", name="ck_charging_step_duration"
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", "command_id", name="uq_charging_step_command"),
    )
    op.create_index(
        "ix_charging_command_steps_vehicle_id", "charging_command_steps", ["vehicle_id"]
    )
    op.create_index(
        "ix_charging_command_steps_requested_by_user_id",
        "charging_command_steps",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("charging_command_steps")
    op.drop_table("charging_system_states")
