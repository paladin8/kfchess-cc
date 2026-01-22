"""Add game_replays table.

Revision ID: 001_add_game_replays
Revises:
Create Date: 2025-01-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_add_game_replays"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create game_replays table."""
    op.create_table(
        "game_replays",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("speed", sa.String(), nullable=False),
        sa.Column("board_type", sa.String(), nullable=False),
        sa.Column("players", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("moves", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("total_ticks", sa.Integer(), nullable=False),
        sa.Column("winner", sa.Integer(), nullable=True),
        sa.Column("win_reason", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_public", sa.Boolean(), server_default="true", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add index on created_at for efficient sorting by recency
    op.create_index("ix_game_replays_created_at", "game_replays", ["created_at"])


def downgrade() -> None:
    """Drop game_replays table."""
    op.drop_index("ix_game_replays_created_at", "game_replays")
    op.drop_table("game_replays")
