"""Add users and oauth_accounts tables.

Revision ID: 002_add_users
Revises: 001_add_game_replays
Create Date: 2025-01-22

This migration handles two scenarios:
1. Fresh install: Create new users table with all columns
2. Legacy migration: Add new columns to existing users table

Legacy users (all Google OAuth) have their email copied to google_id
and are marked as verified since they authenticated via Google.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_add_users"
down_revision: str | None = "001_add_game_replays"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create or upgrade users table, create oauth_accounts table."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "users" in tables:
        # Legacy migration path: add new columns to existing table
        _migrate_legacy_users(inspector)
    else:
        # Fresh install path: create new table
        _create_users_table()

    # Always create oauth_accounts table (new)
    _create_oauth_accounts_table()


def _create_users_table() -> None:
    """Create users table for fresh install."""
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("picture_url", sa.String(), nullable=True),
        sa.Column("google_id", sa.String(255), nullable=True),
        sa.Column(
            "ratings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_online", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("google_id", name="uq_users_google_id"),
    )

    # Create indexes
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_google_id", "users", ["google_id"])


def _migrate_legacy_users(inspector: sa.Inspector) -> None:
    """Add new columns to existing users table from legacy system."""
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    # Add new authentication columns if they don't exist
    if "hashed_password" not in existing_columns:
        op.add_column(
            "users", sa.Column("hashed_password", sa.String(255), nullable=True)
        )

    if "google_id" not in existing_columns:
        op.add_column(
            "users", sa.Column("google_id", sa.String(255), nullable=True)
        )

    if "is_active" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        )

    if "is_verified" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "is_verified", sa.Boolean(), server_default="false", nullable=False
            ),
        )

    if "is_superuser" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "is_superuser", sa.Boolean(), server_default="false", nullable=False
            ),
        )

    # Handle timestamp column renames (join_time -> created_at)
    if "join_time" in existing_columns and "created_at" not in existing_columns:
        op.alter_column("users", "join_time", new_column_name="created_at")

    if "created_at" not in existing_columns and "join_time" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )

    if "last_online" not in existing_columns:
        op.add_column(
            "users",
            sa.Column(
                "last_online", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
        )

    # Migrate data: copy email to google_id for existing users
    # All legacy users are Google OAuth, so their email IS their Google identifier
    # Mark them as verified since they authenticated via Google
    op.execute(
        """
        UPDATE users
        SET google_id = email,
            is_verified = true,
            is_active = true
        WHERE google_id IS NULL AND email IS NOT NULL
    """
    )

    # Add unique constraint and index for google_id
    op.create_unique_constraint("uq_users_google_id", "users", ["google_id"])
    op.create_index("ix_users_google_id", "users", ["google_id"])

    # Drop legacy current_game column if it exists (now using Redis)
    if "current_game" in existing_columns:
        op.drop_column("users", "current_game")


def _create_oauth_accounts_table() -> None:
    """Create oauth_accounts table for FastAPI-Users OAuth support."""
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("oauth_name", sa.String(100), nullable=False),
        sa.Column("access_token", sa.String(1024), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=True),
        sa.Column("refresh_token", sa.String(1024), nullable=True),
        sa.Column("account_id", sa.String(320), nullable=False),
        sa.Column("account_email", sa.String(320), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "user_id", "oauth_name", name="oauth_accounts_user_provider_unique"
        ),
    )

    # Create indexes
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])
    op.create_index(
        "ix_oauth_accounts_provider", "oauth_accounts", ["oauth_name", "account_id"]
    )


def downgrade() -> None:
    """Drop oauth_accounts table and remove user auth columns.

    Note: This does NOT drop the users table to preserve user data.
    It only removes the columns added by this migration.
    """
    # Drop oauth_accounts table
    op.drop_index("ix_oauth_accounts_provider", "oauth_accounts")
    op.drop_index("ix_oauth_accounts_user_id", "oauth_accounts")
    op.drop_table("oauth_accounts")

    # Remove columns added to users table
    # Note: We don't drop the entire users table to preserve data
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    # Drop index and constraint for google_id
    op.drop_index("ix_users_google_id", "users")
    op.drop_constraint("uq_users_google_id", "users", type_="unique")

    # Drop added columns
    columns_to_drop = [
        "hashed_password",
        "google_id",
        "is_active",
        "is_verified",
        "is_superuser",
    ]
    for col in columns_to_drop:
        if col in existing_columns:
            op.drop_column("users", col)
