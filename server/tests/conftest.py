"""Pytest configuration and fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient

from kfchess.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
