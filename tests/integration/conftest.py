"""Integration-test fixtures.

All integration tests share a single event-loop so that the module-level
SQLAlchemy async engine pool and Redis pool (both created at import time)
remain valid across the entire test session.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def client() -> AsyncClient:  # type: ignore[override]
    """Session-scoped async HTTP client — keeps the engine pool alive."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
