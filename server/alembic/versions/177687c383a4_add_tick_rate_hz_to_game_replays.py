"""Add tick_rate_hz to game_replays

Revision ID: 177687c383a4
Revises: 005_add_elo_rating
Create Date: 2026-01-27 01:03:50.043969

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '177687c383a4'
down_revision: Union[str, None] = '005_add_elo_rating'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tick_rate_hz column with default of 10 for existing replays
    # (all existing replays were recorded at 10 Hz)
    op.add_column(
        'game_replays',
        sa.Column('tick_rate_hz', sa.Integer(), nullable=False, server_default='10')
    )


def downgrade() -> None:
    op.drop_column('game_replays', 'tick_rate_hz')
