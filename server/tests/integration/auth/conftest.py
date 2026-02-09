"""Fixtures for auth integration tests."""

import pytest
from sqlalchemy import delete


@pytest.fixture(autouse=True)
async def cleanup_test_users():
    """Clean up test users created during tests.

    Runs before and after each test to ensure clean state.
    Deletes users with emails matching 'test_%@example.com' pattern.
    """
    from kfchess.db.models import OAuthAccount, User
    from kfchess.db.session import async_session_factory

    async def _cleanup():
        async with async_session_factory() as session:
            # Delete OAuth accounts for test users first (foreign key constraint)
            await session.execute(
                delete(OAuthAccount).where(
                    OAuthAccount.account_email.like("test_%@example.com")
                )
            )
            # Delete test users
            await session.execute(
                delete(User).where(User.email.like("test_%@example.com"))
            )
            await session.commit()

    # Clean up before test (in case previous run left data)
    await _cleanup()

    yield

    # Clean up after test
    await _cleanup()


@pytest.fixture(autouse=True)
async def reset_db_engine():
    """Reset the database engine after each test.

    This ensures each test gets a fresh connection pool tied to the
    current event loop, avoiding "attached to different loop" errors.
    """
    yield

    # Dispose the engine after each test to clean up connections
    from kfchess.db import session as db_session

    if db_session._engine is not None:
        await db_session._engine.dispose()

        # Recreate the engine for the next test
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from kfchess.settings import get_settings

        db_session._engine = create_async_engine(
            get_settings().database_url,
            echo=False,
            pool_pre_ping=True,
        )
        db_session.async_session_factory = async_sessionmaker(
            db_session._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
