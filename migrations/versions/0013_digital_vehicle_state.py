"""Add the versioned digital-vehicle state aggregate."""

import sqlalchemy as sa
from alembic import op

revision = "0013_digital_vehicle_state"
down_revision = "0012_test_artifacts"
branch_labels = None
depends_on = None


BASELINE = {
    "operational_mode": "parked",
    "battery": {
        "state_of_charge_pct": 80.0,
        "state_of_health_pct": 100.0,
        "pack_voltage_v": 400.0,
        "pack_current_a": 0.0,
        "temperature_c": 22.0,
        "contactors_closed": False,
        "charging_status": "disconnected",
    },
    "powertrain": {
        "motor_enabled": False,
        "gear": "park",
        "speed_kph": 0.0,
        "requested_torque_nm": 0.0,
        "delivered_torque_nm": 0.0,
    },
    "brakes": {
        "pedal_pct": 0.0,
        "hydraulic_pressure_bar": 0.0,
        "parking_brake_applied": True,
        "abs_active": False,
    },
    "steering": {"wheel_angle_deg": 0.0, "assist_active": False},
    "lighting": {"exterior_mode": "off", "brake_lights": False, "indicator": "off"},
}


def upgrade() -> None:
    op.create_table(
        "vehicle_digital_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("operational_mode", sa.String(20), nullable=False),
        sa.Column("battery_state", sa.JSON(), nullable=False),
        sa.Column("powertrain_state", sa.JSON(), nullable=False),
        sa.Column("brake_state", sa.JSON(), nullable=False),
        sa.Column("steering_state", sa.JSON(), nullable=False),
        sa.Column("lighting_state", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id"),
    )
    op.create_index(
        "ix_vehicle_digital_states_vehicle_id", "vehicle_digital_states", ["vehicle_id"]
    )
    states = sa.table(
        "vehicle_digital_states",
        sa.column("id", sa.Uuid()),
        sa.column("vehicle_id", sa.Uuid()),
        sa.column("operational_mode", sa.String()),
        sa.column("battery_state", sa.JSON()),
        sa.column("powertrain_state", sa.JSON()),
        sa.column("brake_state", sa.JSON()),
        sa.column("steering_state", sa.JSON()),
        sa.column("lighting_state", sa.JSON()),
        sa.column("version", sa.Integer()),
    )
    vehicles = sa.table("vehicles", sa.column("id", sa.Uuid()))
    op.execute(
        states.insert().from_select(
            [
                "id",
                "vehicle_id",
                "operational_mode",
                "battery_state",
                "powertrain_state",
                "brake_state",
                "steering_state",
                "lighting_state",
                "version",
            ],
            sa.select(
                sa.func.gen_random_uuid(),
                vehicles.c.id,
                sa.literal(BASELINE["operational_mode"]),
                sa.literal(BASELINE["battery"], type_=sa.JSON()),
                sa.literal(BASELINE["powertrain"], type_=sa.JSON()),
                sa.literal(BASELINE["brakes"], type_=sa.JSON()),
                sa.literal(BASELINE["steering"], type_=sa.JSON()),
                sa.literal(BASELINE["lighting"], type_=sa.JSON()),
                sa.literal(1),
            ).select_from(vehicles),
        )
    )


def downgrade() -> None:
    op.drop_index("ix_vehicle_digital_states_vehicle_id", table_name="vehicle_digital_states")
    op.drop_table("vehicle_digital_states")
