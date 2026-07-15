"""Add indexes for bounded audit search and export."""

from alembic import op

revision = "0004_audit_query_indexes"
down_revision = "0003_refresh_token_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_audit_records_created_at_id", "audit_records", ["created_at", "id"])
    op.create_index(
        "ix_audit_records_actor_created_at",
        "audit_records",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_audit_records_resource_created_at",
        "audit_records",
        ["resource_type", "resource_id", "created_at"],
    )
    op.create_index("ix_audit_records_correlation_id", "audit_records", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_records_correlation_id", table_name="audit_records")
    op.drop_index("ix_audit_records_resource_created_at", table_name="audit_records")
    op.drop_index("ix_audit_records_actor_created_at", table_name="audit_records")
    op.drop_index("ix_audit_records_created_at_id", table_name="audit_records")
