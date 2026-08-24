"""Add the versioned electronic control unit aggregate."""

import sqlalchemy as sa
from alembic import op

revision = "0018_ecu_aggregate"
down_revision = "0017_simulation_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "electronic_control_units",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("identifier", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("ecu_type", sa.String(30), nullable=False),
        sa.Column("operational_state", sa.String(20), nullable=False),
        sa.Column("memory", sa.JSON(), nullable=False),
        sa.Column("faults", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", "identifier", name="uq_ecu_vehicle_identifier"),
    )
    op.create_index(
        "ix_electronic_control_units_vehicle_id", "electronic_control_units", ["vehicle_id"]
    )
    op.create_index(
        "ix_electronic_control_units_ecu_type", "electronic_control_units", ["ecu_type"]
    )
    op.create_index(
        "ix_electronic_control_units_operational_state",
        "electronic_control_units",
        ["operational_state"],
    )


def downgrade() -> None:
    op.drop_table("electronic_control_units")
