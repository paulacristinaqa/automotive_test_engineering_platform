"""Add ECU signal contracts and gateway routing hooks."""

import sqlalchemy as sa
from alembic import op

revision = "0022_ecu_signal_contracts"
down_revision = "0021_ecu_memory_regions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "electronic_control_units",
        sa.Column("signals", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "ecu_signal_routes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("gateway_ecu_id", sa.Uuid(), nullable=False),
        sa.Column("identifier", sa.String(80), nullable=False),
        sa.Column("source_ecu_id", sa.Uuid(), nullable=False),
        sa.Column("source_signal", sa.String(40), nullable=False),
        sa.Column("target_ecu_id", sa.Uuid(), nullable=False),
        sa.Column("target_signal", sa.String(40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["gateway_ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "gateway_ecu_id", "identifier", name="uq_ecu_signal_route_identifier"
        ),
    )
    op.create_index("ix_ecu_signal_routes_gateway_ecu_id", "ecu_signal_routes", ["gateway_ecu_id"])
    op.create_index("ix_ecu_signal_routes_source_ecu_id", "ecu_signal_routes", ["source_ecu_id"])
    op.create_index("ix_ecu_signal_routes_target_ecu_id", "ecu_signal_routes", ["target_ecu_id"])


def downgrade() -> None:
    op.drop_table("ecu_signal_routes")
    op.drop_column("electronic_control_units", "signals")
