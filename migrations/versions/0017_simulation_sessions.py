"""Add multi-vehicle simulation sessions and snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0017_simulation_sessions"
down_revision = "0016_vehicle_dynamics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vehicle_simulation_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_vehicle_simulation_sessions_created_by_user_id",
        "vehicle_simulation_sessions",
        ["created_by_user_id"],
    )
    op.create_table(
        "vehicle_simulation_session_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["vehicle_simulation_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "vehicle_id", name="uq_simulation_session_vehicle"),
    )
    op.create_index(
        "ix_vehicle_simulation_session_members_session_id",
        "vehicle_simulation_session_members",
        ["session_id"],
    )
    op.create_index(
        "ix_vehicle_simulation_session_members_vehicle_id",
        "vehicle_simulation_session_members",
        ["vehicle_id"],
    )
    op.create_table(
        "vehicle_simulation_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("states", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["vehicle_simulation_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "snapshot_id", name="uq_simulation_session_snapshot"),
    )
    op.create_index(
        "ix_vehicle_simulation_snapshots_session_id", "vehicle_simulation_snapshots", ["session_id"]
    )
    op.create_index(
        "ix_vehicle_simulation_snapshots_created_by_user_id",
        "vehicle_simulation_snapshots",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("vehicle_simulation_snapshots")
    op.drop_table("vehicle_simulation_session_members")
    op.drop_table("vehicle_simulation_sessions")
