"""Add the vehicle catalogue and idempotent telemetry ingestion store."""

import sqlalchemy as sa
from alembic import op

revision = "0007_vehicle_telemetry"
down_revision = "0006_module_heartbeat_leases"
branch_labels = None
depends_on = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "vehicles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identifier", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identifier"),
    )
    op.create_index("ix_vehicles_identifier", "vehicles", ["identifier"])
    op.create_index("ix_vehicles_status", "vehicles", ["status"])
    op.create_table(
        "vehicle_telemetry_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("source_module_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("property_name", sa.String(120), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("unit", sa.String(40), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["source_module_id"], ["platform_modules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_vehicle_telemetry_events_event_id"),
    )
    for column in ("event_id", "vehicle_id", "source_module_id", "property_name", "observed_at"):
        op.create_index(
            f"ix_vehicle_telemetry_events_{column}", "vehicle_telemetry_events", [column]
        )


def downgrade() -> None:
    for column in ("observed_at", "property_name", "source_module_id", "vehicle_id", "event_id"):
        op.drop_index(
            f"ix_vehicle_telemetry_events_{column}", table_name="vehicle_telemetry_events"
        )
    op.drop_table("vehicle_telemetry_events")
    op.drop_index("ix_vehicles_status", table_name="vehicles")
    op.drop_index("ix_vehicles_identifier", table_name="vehicles")
    op.drop_table("vehicles")
