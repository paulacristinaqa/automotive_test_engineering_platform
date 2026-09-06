"""Add cross-domain electric-vehicle scenario evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0043_electric_vehicle_scenarios"
down_revision = "0042_range_estimation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "electric_vehicle_scenario_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.String(40), nullable=False),
        sa.Column("scenario_type", sa.String(40), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", "execution_id", name="uq_electric_vehicle_scenario"),
    )
    op.create_index(
        "ix_electric_vehicle_scenario_executions_vehicle_id",
        "electric_vehicle_scenario_executions",
        ["vehicle_id"],
    )
    op.create_index(
        "ix_electric_vehicle_scenario_executions_scenario_type",
        "electric_vehicle_scenario_executions",
        ["scenario_type"],
    )
    op.create_index(
        "ix_electric_vehicle_scenario_executions_status",
        "electric_vehicle_scenario_executions",
        ["status"],
    )
    op.create_index(
        "ix_electric_vehicle_scenario_executions_requested_by_user_id",
        "electric_vehicle_scenario_executions",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("electric_vehicle_scenario_executions")
