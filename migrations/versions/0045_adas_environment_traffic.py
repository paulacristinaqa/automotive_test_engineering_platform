"""Add ADAS environment and traffic control ground truth."""

import sqlalchemy as sa
from alembic import op

revision = "0045_adas_environment_traffic"
down_revision = "0044_adas_world_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "adas_world_scenes",
        sa.Column("environment", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
    )
    op.add_column(
        "adas_world_scenes",
        sa.Column(
            "traffic_controls", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("adas_world_scenes", "traffic_controls")
    op.drop_column("adas_world_scenes", "environment")
