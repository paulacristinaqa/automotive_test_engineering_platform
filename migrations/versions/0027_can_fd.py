"""Add CAN FD network and frame metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0027_can_fd"
down_revision = "0026_can_dbc_codec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "can_networks",
        sa.Column(
            "can_fd_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.add_column(
        "can_networks", sa.Column("data_bitrate_kbps", sa.Integer(), nullable=True)
    )
    op.add_column(
        "can_frame_transmissions",
        sa.Column(
            "protocol", sa.String(16), server_default="classic", nullable=False
        ),
    )
    op.add_column(
        "can_frame_transmissions",
        sa.Column(
            "bitrate_switch", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("can_frame_transmissions", "bitrate_switch")
    op.drop_column("can_frame_transmissions", "protocol")
    op.drop_column("can_networks", "data_bitrate_kbps")
    op.drop_column("can_networks", "can_fd_enabled")
