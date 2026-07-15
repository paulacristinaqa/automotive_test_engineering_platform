"""Add workload credentials and heartbeat leases to the module registry."""

import sqlalchemy as sa
from alembic import op

revision = "0006_module_heartbeat_leases"
down_revision = "0005_module_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_modules",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "platform_modules",
        sa.Column("lease_duration_seconds", sa.Integer(), server_default="60", nullable=False),
    )
    op.add_column(
        "platform_modules",
        sa.Column("heartbeat_token_hash", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        "ck_platform_modules_lease_duration",
        "platform_modules",
        "lease_duration_seconds BETWEEN 5 AND 3600",
    )
    op.create_index(
        "ix_platform_modules_lease_expires_at", "platform_modules", ["lease_expires_at"]
    )
    op.alter_column("audit_records", "actor_user_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.alter_column("audit_records", "actor_user_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_index("ix_platform_modules_lease_expires_at", table_name="platform_modules")
    op.drop_constraint("ck_platform_modules_lease_duration", "platform_modules", type_="check")
    op.drop_column("platform_modules", "heartbeat_token_hash")
    op.drop_column("platform_modules", "lease_duration_seconds")
    op.drop_column("platform_modules", "lease_expires_at")
