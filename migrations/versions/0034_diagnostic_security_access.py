"""Add deterministic UDS Security Access state."""

import sqlalchemy as sa
from alembic import op

revision = "0034_diagnostic_security_access"
down_revision = "0033_diagnostic_routines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_security_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ecu_id", sa.Uuid(), nullable=False),
        sa.Column("challenge_counter", sa.Integer(), nullable=False),
        sa.Column("expected_key_digest", sa.String(64), nullable=True),
        sa.Column("seed_expires_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until_ms", sa.BigInteger(), nullable=True),
        sa.Column("target_level", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("challenge_counter >= 0", name="ck_diagnostic_security_counter"),
        sa.CheckConstraint(
            "failed_attempts >= 0 AND failed_attempts <= 3",
            name="ck_diagnostic_security_attempts",
        ),
        sa.CheckConstraint(
            "target_level IN (0, 1)", name="ck_diagnostic_security_target_level"
        ),
        sa.CheckConstraint("version >= 1", name="ck_diagnostic_security_version"),
        sa.ForeignKeyConstraint(["ecu_id"], ["electronic_control_units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ecu_id", name="uq_diagnostic_security_ecu"),
    )
    op.create_index(
        "ix_diagnostic_security_states_ecu_id", "diagnostic_security_states", ["ecu_id"]
    )


def downgrade() -> None:
    op.drop_table("diagnostic_security_states")
