"""Add immutable audit records for administrative actions."""

import sqlalchemy as sa
from alembic import op

revision = "0002_user_administration_audit"
down_revision = "0001_core_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(160), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_records_action", "audit_records", ["action"])
    op.execute(
        """
        CREATE FUNCTION atep_prevent_audit_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit records are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_records_immutable
        BEFORE UPDATE OR DELETE ON audit_records
        FOR EACH ROW EXECUTE FUNCTION atep_prevent_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_records_immutable ON audit_records")
    op.execute("DROP FUNCTION IF EXISTS atep_prevent_audit_mutation()")
    op.drop_index("ix_audit_records_action", table_name="audit_records")
    op.drop_table("audit_records")
