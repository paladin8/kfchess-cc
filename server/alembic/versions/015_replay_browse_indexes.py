"""Improve replay browse indexes with partial indexes.

Revision ID: 015_replay_browse_indexes
Revises: 014_add_active_games
Create Date: 2026-02-10

Replaces the existing created_at and top indexes with partial indexes
that match the exact query predicates (is_public=true, like_count>0),
allowing PostgreSQL to use index-only scans for browse queries.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015_replay_browse_indexes"
down_revision: str | None = "014_add_active_games"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Replace created_at index with partial index filtered to public replays
    op.drop_index("ix_game_replays_created_at", "game_replays")
    op.create_index(
        "ix_game_replays_recent",
        "game_replays",
        [sa.text("created_at DESC")],
        postgresql_where=sa.text("is_public = true"),
    )

    # Replace top index with partial index filtered to public replays with likes
    op.drop_index("ix_game_replays_top", "game_replays")
    op.create_index(
        "ix_game_replays_top",
        "game_replays",
        [sa.text("like_count DESC"), sa.text("created_at DESC")],
        postgresql_where=sa.text("is_public = true AND like_count > 0"),
    )


def downgrade() -> None:
    # Restore original top index
    op.drop_index("ix_game_replays_top", "game_replays")
    op.create_index(
        "ix_game_replays_top",
        "game_replays",
        ["like_count", "created_at"],
        postgresql_ops={"like_count": "DESC", "created_at": "DESC"},
    )

    # Restore original created_at index
    op.drop_index("ix_game_replays_recent", "game_replays")
    op.create_index(
        "ix_game_replays_created_at",
        "game_replays",
        ["created_at"],
    )
