"""Add explainable root cause, risk, and prediction evaluation evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0062_ai_root_cause_risk"
down_revision = "0061_ai_test_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_root_cause_risk_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("hypotheses", sa.JSON(), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_band", sa.String(16), nullable=False),
        sa.Column("predicted_failure", sa.Boolean(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("evaluation_id", sa.String(64), nullable=True),
        sa.Column("evaluation_hash", sa.String(64), nullable=True),
        sa.Column("evaluated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("actual_failure", sa.Boolean(), nullable=True),
        sa.Column("confirmed_hypothesis_code", sa.String(64), nullable=True),
        sa.Column("evaluation_evidence_refs", sa.JSON(), nullable=True),
        sa.Column("prediction_correct", sa.Boolean(), nullable=True),
        sa.Column("brier_score", sa.Float(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("horizon_hours BETWEEN 1 AND 720", name="root_risk_horizon"),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="root_risk_score"),
        sa.CheckConstraint("version >= 1", name="root_risk_version"),
        sa.CheckConstraint(
            "risk_band IN ('low', 'medium', 'high', 'critical')", name="root_risk_band"
        ),
        sa.CheckConstraint(
            "brier_score IS NULL OR (brier_score >= 0 AND brier_score <= 1)",
            name="root_risk_brier",
        ),
        sa.ForeignKeyConstraint(["request_id"], ["ai_analysis_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evaluated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", name="uq_ai_root_cause_risk_analyses_analysis_id"),
        sa.UniqueConstraint("request_id", name="uq_ai_root_cause_risk_analyses_request_id"),
        sa.UniqueConstraint("evaluation_id", name="uq_ai_root_cause_risk_analyses_evaluation_id"),
    )
    for column in (
        "analysis_id",
        "request_id",
        "created_by_user_id",
        "risk_score",
        "risk_band",
    ):
        op.create_index(
            f"ix_ai_root_cause_risk_analyses_{column}",
            "ai_root_cause_risk_analyses",
            [column],
        )


def downgrade() -> None:
    op.drop_table("ai_root_cause_risk_analyses")
