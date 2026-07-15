"""Add the platform module registry and capability catalogue."""

import sqlalchemy as sa
from alembic import op

revision = "0005_module_registry"
down_revision = "0004_audit_query_indexes"
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
        "platform_modules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_platform_modules_name", "platform_modules", ["name"])
    op.create_index("ix_platform_modules_status", "platform_modules", ["status"])
    op.create_table(
        "module_capabilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["module_id"], ["platform_modules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_id", "name", name="uq_module_capabilities_module_name"),
    )
    op.create_index("ix_module_capabilities_module_id", "module_capabilities", ["module_id"])
    op.create_index("ix_module_capabilities_name", "module_capabilities", ["name"])


def downgrade() -> None:
    op.drop_index("ix_module_capabilities_name", table_name="module_capabilities")
    op.drop_index("ix_module_capabilities_module_id", table_name="module_capabilities")
    op.drop_table("module_capabilities")
    op.drop_index("ix_platform_modules_status", table_name="platform_modules")
    op.drop_index("ix_platform_modules_name", table_name="platform_modules")
    op.drop_table("platform_modules")
