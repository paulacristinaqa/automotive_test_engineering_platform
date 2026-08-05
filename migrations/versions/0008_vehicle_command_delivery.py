"""Add leased and acknowledged vehicle command delivery."""

import sqlalchemy as sa
from alembic import op

revision = "0008_vehicle_command_delivery"
down_revision = "0007_vehicle_telemetry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vehicle_commands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.String(64), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("target_module_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("test_run_id", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token_hash", sa.String(64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_module_id"], ["platform_modules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id", name="uq_vehicle_commands_command_id"),
    )
    for column in (
        "command_id",
        "vehicle_id",
        "target_module_id",
        "requested_by_user_id",
        "test_run_id",
        "kind",
        "status",
        "available_at",
        "leased_until",
    ):
        op.create_index(f"ix_vehicle_commands_{column}", "vehicle_commands", [column])


def downgrade() -> None:
    for column in (
        "leased_until",
        "available_at",
        "status",
        "kind",
        "test_run_id",
        "requested_by_user_id",
        "target_module_id",
        "vehicle_id",
        "command_id",
    ):
        op.drop_index(f"ix_vehicle_commands_{column}", table_name="vehicle_commands")
    op.drop_table("vehicle_commands")
