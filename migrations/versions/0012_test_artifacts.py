"""Add immutable test-artifact metadata for object-backed evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0012_test_artifacts"
down_revision = "0011_test_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "test_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("test_run_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.String(64), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("test_run_id", "artifact_id", name="uq_test_artifacts_run_artifact_id"),
        sa.UniqueConstraint("object_key", name="uq_test_artifacts_object_key"),
    )
    for column in (
        "test_run_id",
        "artifact_id",
        "uploaded_by_user_id",
        "kind",
        "sha256",
    ):
        op.create_index(f"ix_test_artifacts_{column}", "test_artifacts", [column])


def downgrade() -> None:
    for column in ("sha256", "kind", "uploaded_by_user_id", "artifact_id", "test_run_id"):
        op.drop_index(f"ix_test_artifacts_{column}", table_name="test_artifacts")
    op.drop_table("test_artifacts")
