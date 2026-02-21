"""Integration tests for auth flow (requires running PG + Redis).

Run: uv run pytest tests/integration/test_auth_flow.py -v
Pre-condition: make up && make migrate
"""

import uuid

import pytest
from httpx import AsyncClient

# All tests in this module share the session-scoped event loop so that the
# module-level SQLAlchemy async engine pool stays alive across tests.
pytestmark = pytest.mark.asyncio(loop_scope="session")


def unique_user() -> dict[str, str]:
    """Generate unique credentials to avoid test pollution."""
    uid = uuid.uuid4().hex[:8]
    return {
        "username": f"testuser_{uid}",
        "email": f"test_{uid}@example.com",
        "password": "TestPass1",
    }


class TestRegister:
    async def test_register_success(self, client: AsyncClient) -> None:
        user = unique_user()
        resp = await client.post("/api/v1/auth/register", json=user)
        assert resp.status_code == 201
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["username"] == user["username"]
        assert body["data"]["email"] == user["email"]
        assert "user_id" in body["data"]
        assert "request_id" in body

    async def test_register_duplicate_username(self, client: AsyncClient) -> None:
        user = unique_user()
        await client.post("/api/v1/auth/register", json=user)
        resp = await client.post(
            "/api/v1/auth/register",
            json={**user, "email": "other@example.com"},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == 1001

    async def test_register_duplicate_email(self, client: AsyncClient) -> None:
        user = unique_user()
        await client.post("/api/v1/auth/register", json=user)
        resp = await client.post(
            "/api/v1/auth/register",
            json={**user, "username": f"other_{uuid.uuid4().hex[:6]}"},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == 1002

    async def test_register_weak_password(self, client: AsyncClient) -> None:
        user = unique_user()
        resp = await client.post(
            "/api/v1/auth/register",
            json={**user, "password": "weak"},
        )
        assert resp.status_code == 422


class TestLogin:
    async def test_login_success(self, client: AsyncClient) -> None:
        user = unique_user()
        await client.post("/api/v1/auth/register", json=user)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": user["username"], "password": user["password"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]
        assert body["data"]["token_type"] == "Bearer"

    async def test_login_wrong_password(self, client: AsyncClient) -> None:
        user = unique_user()
        await client.post("/api/v1/auth/register", json=user)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": user["username"], "password": "WrongPass1"},
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == 1003

    async def test_login_unknown_user(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "nobody_xyz", "password": "Pass1word"},
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == 1003


class TestRefresh:
    async def test_refresh_success(self, client: AsyncClient) -> None:
        user = unique_user()
        await client.post("/api/v1/auth/register", json=user)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": user["username"], "password": user["password"]},
        )
        refresh_token = login_resp.json()["data"]["refresh_token"]

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        new_access = resp.json()["data"]["access_token"]
        assert len(new_access) > 20

    async def test_refresh_with_access_token_fails(self, client: AsyncClient) -> None:
        user = unique_user()
        await client.post("/api/v1/auth/register", json=user)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": user["username"], "password": user["password"]},
        )
        access_token = login_resp.json()["data"]["access_token"]

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == 1005

    async def test_refresh_with_garbage_token_fails(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not.a.real.token"},
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == 1005


class TestProtectedRoute:
    async def test_access_with_valid_token(self, client: AsyncClient) -> None:
        """Health check is public, but verify the token workflow end-to-end."""
        user = unique_user()
        await client.post("/api/v1/auth/register", json=user)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": user["username"], "password": user["password"]},
        )
        access_token = login_resp.json()["data"]["access_token"]

        resp = await client.get(
            "/health",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200

    async def test_access_without_token_fails(self, client: AsyncClient) -> None:
        """Placeholder — will be meaningful once a protected endpoint exists."""
        pass
