"""Add reusable test definitions and suites."""

import sqlalchemy as sa
from alembic import op

revision = "0051_test_catalog"
down_revision = "0050_adas_integration_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "test_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("definition_id", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("level", sa.String(24), nullable=False),
        sa.Column("automation_mode", sa.String(16), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("preconditions", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("definition_id", name="uq_test_definitions_definition_id"),
    )
    for column in (
        "definition_id",
        "created_by_user_id",
        "domain",
        "level",
        "automation_mode",
        "status",
    ):
        op.create_index(f"ix_test_definitions_{column}", "test_definitions", [column])

    op.create_table(
        "test_suites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("suite_id", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("suite_type", sa.String(20), nullable=False),
        sa.Column("composition", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("suite_id", name="uq_test_suites_suite_id"),
    )
    for column in ("suite_id", "created_by_user_id", "suite_type", "status"):
        op.create_index(f"ix_test_suites_{column}", "test_suites", [column])


def downgrade() -> None:
    op.drop_table("test_suites")
    op.drop_table("test_definitions")
