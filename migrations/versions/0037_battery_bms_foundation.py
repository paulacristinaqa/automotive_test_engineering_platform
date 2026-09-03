"""Add the electric-vehicle battery and BMS simulation foundation."""

import sqlalchemy as sa
from alembic import op

revision = "0037_battery_bms_foundation"
down_revision = "0036_diagnostic_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "battery_pack_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("chemistry", sa.String(16), nullable=False),
        sa.Column("series_cell_count", sa.Integer(), nullable=False),
        sa.Column("nominal_capacity_ah", sa.Float(), nullable=False),
        sa.Column("nominal_cell_voltage_v", sa.Float(), nullable=False),
        sa.Column("internal_resistance_ohm", sa.Float(), nullable=False),
        sa.Column("soc_pct", sa.Float(), nullable=False),
        sa.Column("soh_pct", sa.Float(), nullable=False),
        sa.Column("pack_voltage_v", sa.Float(), nullable=False),
        sa.Column("pack_current_a", sa.Float(), nullable=False),
        sa.Column("pack_temperature_c", sa.Float(), nullable=False),
        sa.Column("contactor_state", sa.String(16), nullable=False),
        sa.Column("operating_state", sa.String(16), nullable=False),
        sa.Column("cells", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("simulation_time_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "series_cell_count >= 4 AND series_cell_count <= 192",
            name="ck_battery_pack_cells",
        ),
        sa.CheckConstraint("nominal_capacity_ah > 0", name="ck_battery_pack_capacity"),
        sa.CheckConstraint("soc_pct >= 0 AND soc_pct <= 100", name="ck_battery_pack_soc"),
        sa.CheckConstraint("soh_pct >= 0 AND soh_pct <= 100", name="ck_battery_pack_soh"),
        sa.CheckConstraint(
            "contactor_state IN ('open', 'closed')", name="ck_battery_pack_contactor"
        ),
        sa.CheckConstraint(
            "operating_state IN ('normal', 'warning', 'protection')",
            name="ck_battery_pack_operating_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_battery_pack_version"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", name="uq_battery_pack_vehicle"),
    )
    op.create_index("ix_battery_pack_states_vehicle_id", "battery_pack_states", ["vehicle_id"])
    op.create_index("ix_battery_pack_states_chemistry", "battery_pack_states", ["chemistry"])
    op.create_index(
        "ix_battery_pack_states_contactor_state", "battery_pack_states", ["contactor_state"]
    )
    op.create_index(
        "ix_battery_pack_states_operating_state", "battery_pack_states", ["operating_state"]
    )
    op.create_table(
        "battery_simulation_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("requested_current_a", sa.Float(), nullable=False),
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
            "duration_ms >= 1 AND duration_ms <= 3600000", name="ck_battery_step_duration"
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", "command_id", name="uq_battery_step_command"),
    )
    op.create_index(
        "ix_battery_simulation_steps_vehicle_id", "battery_simulation_steps", ["vehicle_id"]
    )
    op.create_index(
        "ix_battery_simulation_steps_requested_by_user_id",
        "battery_simulation_steps",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("battery_simulation_steps")
    op.drop_table("battery_pack_states")
