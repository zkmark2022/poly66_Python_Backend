"""Integration tests for pm_account endpoints (requires running PG + Redis).

Pre-condition: make up && make migrate

Uses the session-scoped client fixture from tests/integration/conftest.py.
All tests share one event loop — avoids asyncpg pool cross-loop error.
"""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_user() -> dict[str, str]:
    uid = uuid.uuid4().hex[:8]
    return {
        "username": f"acct_{uid}",
        "email": f"acct_{uid}@example.com",
        "password": "TestPass1",
    }


async def _register_and_login(client: AsyncClient) -> str:
    """Register a fresh user and return the access token."""
    user = _unique_user()
    await client.post("/api/v1/auth/register", json=user)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": user["username"], "password": user["password"]},
    )
    return str(resp.json()["data"]["access_token"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetBalance:
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/account/balance")
        assert resp.status_code == 401

    async def test_new_user_has_zero_balance(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        resp = await client.get(
            "/api/v1/account/balance",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["available_balance_cents"] == 0
        assert data["frozen_balance_cents"] == 0
        assert data["available_balance_display"] == "$0.00"


class TestDeposit:
    async def test_deposit_increases_balance(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/account/deposit",
            json={"amount_cents": 100000},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["available_balance_cents"] == 100000
        assert data["deposited_cents"] == 100000
        assert data["deposited_display"] == "$1,000.00"
        assert data["ledger_entry_id"] > 0

    async def test_deposit_zero_rejected(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        resp = await client.post(
            "/api/v1/account/deposit",
            json={"amount_cents": 0},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_unauthenticated_deposit_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/account/deposit", json={"amount_cents": 1000})
        assert resp.status_code == 401


class TestWithdraw:
    async def test_withdraw_decreases_balance(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}

        await client.post("/api/v1/account/deposit", json={"amount_cents": 50000}, headers=headers)
        resp = await client.post(
            "/api/v1/account/withdraw",
            json={"amount_cents": 20000},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["available_balance_cents"] == 30000
        assert data["withdrawn_cents"] == 20000
        assert data["ledger_entry_id"] > 0

    async def test_withdraw_insufficient_balance_returns_422(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        resp = await client.post(
            "/api/v1/account/withdraw",
            json={"amount_cents": 1},  # valid amount, but fresh account has zero balance
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == 2001  # InsufficientBalanceError


class TestListLedger:
    async def test_empty_ledger(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        resp = await client.get(
            "/api/v1/account/ledger",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    async def test_deposit_creates_ledger_entry(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}

        await client.post("/api/v1/account/deposit", json={"amount_cents": 5000}, headers=headers)
        resp = await client.get("/api/v1/account/ledger", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["entry_type"] == "DEPOSIT"
        assert items[0]["amount_cents"] == 5000

    async def test_ledger_ordered_descending(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}

        await client.post("/api/v1/account/deposit", json={"amount_cents": 1000}, headers=headers)
        await client.post("/api/v1/account/deposit", json={"amount_cents": 2000}, headers=headers)

        resp = await client.get("/api/v1/account/ledger", headers=headers)
        items = resp.json()["data"]["items"]
        assert len(items) == 2
        # Most recent first (descending by id)
        assert items[0]["id"] > items[1]["id"]

    async def test_unauthenticated_ledger_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/account/ledger")
        assert resp.status_code == 401
