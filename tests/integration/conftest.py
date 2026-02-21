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


@pytest_asyncio.fixture(scope="session")
async def auth_client(client: AsyncClient) -> AsyncClient:
    """Authenticated client — registers a user and injects Bearer token."""
    reg_resp = await client.post("/api/v1/auth/register", json={
        "username": "market_test_user",
        "email": "market_test@example.com",
        "password": "TestPass123!",
    })
    # May already exist if running tests multiple times — that's OK
    _ = reg_resp
    login_resp = await client.post("/api/v1/auth/login", json={
        "username": "market_test_user",
        "password": "TestPass123!",
    })
    token = login_resp.json()["data"]["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
