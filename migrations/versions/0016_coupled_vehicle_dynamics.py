"""Add suspension state for coupled vehicle dynamics."""

import sqlalchemy as sa
from alembic import op

revision = "0016_vehicle_dynamics"
down_revision = "0015_vehicle_sensors"
branch_labels = None
depends_on = None


SUSPENSION_BASELINE = {
    "front_travel_mm": 0.0,
    "rear_travel_mm": 0.0,
    "lateral_acceleration_mps2": 0.0,
}


def upgrade() -> None:
    op.add_column(
        "vehicle_digital_states",
        sa.Column(
            "suspension_state",
            sa.JSON(),
            server_default=sa.text(
                '\'{"front_travel_mm": 0.0, "rear_travel_mm": 0.0, '
                '"lateral_acceleration_mps2": 0.0}\'::json'
            ),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("vehicle_digital_states", "suspension_state")
