"""Add versioned ECU behavior profile state."""

import sqlalchemy as sa
from alembic import op

revision = "0020_ecu_behavior_profiles"
down_revision = "0019_ecu_execution_clock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "electronic_control_units",
        sa.Column("profile_version", sa.String(20), nullable=False, server_default="1.0.0"),
    )
    op.add_column(
        "electronic_control_units",
        sa.Column("behavior_state", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("electronic_control_units", "behavior_state")
    op.drop_column("electronic_control_units", "profile_version")
