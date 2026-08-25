"""Add the typed diagnostic data identifier catalogue."""

import sqlalchemy as sa
from alembic import op

revision = "0032_diagnostic_data_identifiers"
down_revision = "0031_diagnostics_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_data_identifiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ecu_id", sa.Uuid(), nullable=False),
        sa.Column("identifier", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("data_type", sa.String(16), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("writable", sa.Boolean(), nullable=False),
        sa.Column("readable_sessions", sa.JSON(), nullable=False),
        sa.Column("writable_sessions", sa.JSON(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("minimum", sa.Float(), nullable=True),
        sa.Column("maximum", sa.Float(), nullable=True),
        sa.Column("max_length", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "identifier >= 0 AND identifier <= 65535", name="ck_diagnostic_did_identifier"
        ),
        sa.CheckConstraint(
            "data_type IN ('boolean', 'integer', 'decimal', 'string')",
            name="ck_diagnostic_did_data_type",
        ),
        sa.CheckConstraint("version >= 1", name="ck_diagnostic_did_version"),
        sa.CheckConstraint(
            "max_length IS NULL OR max_length >= 1", name="ck_diagnostic_did_max_length"
        ),
        sa.CheckConstraint(
            "minimum IS NULL OR maximum IS NULL OR minimum <= maximum",
            name="ck_diagnostic_did_numeric_range",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecu_id", "identifier", name="uq_diagnostic_data_identifier"),
    )
    op.create_index(
        "ix_diagnostic_data_identifiers_ecu_id", "diagnostic_data_identifiers", ["ecu_id"]
    )
    op.create_index(
        "ix_diagnostic_data_identifiers_identifier",
        "diagnostic_data_identifiers",
        ["identifier"],
    )
    op.create_index(
        "ix_diagnostic_data_identifiers_data_type",
        "diagnostic_data_identifiers",
        ["data_type"],
    )
    op.create_index(
        "ix_diagnostic_data_identifiers_created_by_user_id",
        "diagnostic_data_identifiers",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("diagnostic_data_identifiers")
