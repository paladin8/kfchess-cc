"""Add performance indexes for lobbies.

Revision ID: 004_add_lobby_indexes
Revises: 003_add_lobbies
Create Date: 2025-01-23

This migration adds additional indexes for common query patterns:
- created_at: For ordering lobbies by creation time and cleanup queries
- Composite (is_public, status, created_at): For list_public_waiting() queries
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_add_lobby_indexes"
down_revision: str | None = "003_add_lobbies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add performance indexes for lobbies table."""
    # Index on created_at for ordering and cleanup queries
    op.create_index("ix_lobbies_created_at", "lobbies", ["created_at"])

    # Composite index for list_public_waiting() query pattern:
    # WHERE is_public = true AND status = 'waiting' ORDER BY created_at DESC
    op.create_index(
        "ix_lobbies_public_waiting",
        "lobbies",
        ["is_public", "status", "created_at"],
    )


def downgrade() -> None:
    """Remove performance indexes."""
    op.drop_index("ix_lobbies_public_waiting", "lobbies")
    op.drop_index("ix_lobbies_created_at", "lobbies")
