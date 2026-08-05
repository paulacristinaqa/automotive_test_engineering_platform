"""Add versioned environment profiles and reproducible test-run snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0010_environment_profiles"
down_revision = "0009_test_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "environment_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("vehicle_kind", sa.String(24), nullable=False),
        sa.Column("property_source", sa.String(24), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", name="uq_environment_profiles_profile_id"),
    )
    for column in (
        "profile_id",
        "created_by_user_id",
        "vehicle_kind",
        "property_source",
        "status",
    ):
        op.create_index(f"ix_environment_profiles_{column}", "environment_profiles", [column])

    op.add_column("test_runs", sa.Column("environment_profile_id", sa.Uuid(), nullable=True))
    op.add_column(
        "test_runs", sa.Column("environment_profile_version", sa.Integer(), nullable=True)
    )
    op.add_column("test_runs", sa.Column("environment_snapshot", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_test_runs_environment_profile_id_environment_profiles",
        "test_runs",
        "environment_profiles",
        ["environment_profile_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_test_runs_environment_profile_id", "test_runs", ["environment_profile_id"])


def downgrade() -> None:
    op.drop_index("ix_test_runs_environment_profile_id", table_name="test_runs")
    op.drop_constraint(
        "fk_test_runs_environment_profile_id_environment_profiles",
        "test_runs",
        type_="foreignkey",
    )
    op.drop_column("test_runs", "environment_snapshot")
    op.drop_column("test_runs", "environment_profile_version")
    op.drop_column("test_runs", "environment_profile_id")
    for column in (
        "status",
        "property_source",
        "vehicle_kind",
        "created_by_user_id",
        "profile_id",
    ):
        op.drop_index(f"ix_environment_profiles_{column}", table_name="environment_profiles")
    op.drop_table("environment_profiles")
