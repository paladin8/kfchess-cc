"""Fixtures for integration tests.

These tests require a running PostgreSQL database. They use the same
database as development but clean up after themselves.

To run integration tests:
    uv run pytest tests/integration -v

To run only unit tests (faster, no database required):
    uv run pytest tests/unit -v

To run all tests:
    uv run pytest tests/ -v
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kfchess.settings import get_settings


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require database)"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-mark all tests in this directory as integration tests."""
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


def generate_test_id() -> str:
    """Generate a unique test ID to avoid collisions.

    Must be <= 10 chars to fit the lobby code column.
    """
    return f"T{uuid.uuid4().hex[:5].upper()}"  # "T" + 5 chars = 6 chars


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh database session for each test.

    Creates a new engine and session for each test to avoid
    event loop issues with shared connection pools.
    """
    # Create a fresh engine for this test to avoid event loop issues
    engine = create_async_engine(
        get_settings().database_url,
        echo=False,
        pool_pre_ping=True,
    )

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

    # Dispose of the engine to clean up connections
    await engine.dispose()


@pytest.fixture
def test_game_id() -> str:
    """Generate a unique game ID for testing."""
    return generate_test_id()
