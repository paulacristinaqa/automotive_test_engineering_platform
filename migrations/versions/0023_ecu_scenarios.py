"""Add deterministic multi-ECU scenario execution evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0023_ecu_scenarios"
down_revision = "0022_ecu_signal_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ecu_scenario_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.String(40), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("iteration_count", sa.Integer(), nullable=False),
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
        sa.UniqueConstraint("vehicle_id", "execution_id", name="uq_ecu_scenario_execution"),
    )
    op.create_index(
        "ix_ecu_scenario_executions_vehicle_id", "ecu_scenario_executions", ["vehicle_id"]
    )
    op.create_index(
        "ix_ecu_scenario_executions_requested_by_user_id",
        "ecu_scenario_executions",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("ecu_scenario_executions")
