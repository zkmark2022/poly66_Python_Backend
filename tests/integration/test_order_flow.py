# tests/integration/test_order_flow.py
"""Integration tests for the full order flow: place → match → cancel → idempotency.

Requires a running PostgreSQL DB with migrations applied (make up && make migrate).
Seed data provides three ACTIVE markets:
  - MKT-BTC-100K-2026
  - MKT-ETH-10K-2026
  - MKT-FED-RATE-CUT-2026Q2

Each test creates its own fresh user(s) via register+login to avoid state pollution
across tests (same pattern as test_account_flow.py and test_auth_flow.py).
"""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTIVE_MARKET_ID = "MKT-BTC-100K-2026"
DEPOSIT_AMOUNT = 1_000_000  # $10,000 — enough for any test order


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_user() -> dict[str, str]:
    uid = uuid.uuid4().hex[:8]
    return {
        "username": f"order_{uid}",
        "email": f"order_{uid}@example.com",
        "password": "TestPass123!",
    }


async def _register_and_login(client: AsyncClient) -> str:
    """Register a fresh user and return the Bearer token."""
    user = _unique_user()
    await client.post("/api/v1/auth/register", json=user)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": user["username"], "password": user["password"]},
    )
    return str(resp.json()["data"]["access_token"])


async def _fund_user(client: AsyncClient, token: str, amount: int = DEPOSIT_AMOUNT) -> None:
    """Deposit funds so the user can place buy orders."""
    await client.post(
        "/api/v1/account/deposit",
        json={"amount_cents": amount},
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# TestPlaceOrder
# ---------------------------------------------------------------------------


class TestPlaceOrder:
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": "anon-order-1",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 50,
                "quantity": 5,
            },
        )
        assert resp.status_code == 401

    async def test_gtc_buy_yes_no_match_hangs_in_book(self, client: AsyncClient) -> None:
        """A GTC BUY YES order with no resting asks goes OPEN with no trades."""
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"gtc-buy-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 40,
                "quantity": 5,
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        order = data["order"]
        assert order["status"] == "OPEN"
        assert order["side"] == "YES"
        assert order["direction"] == "BUY"
        assert order["price_cents"] == 40
        assert order["quantity"] == 5
        assert order["filled_quantity"] == 0
        assert order["remaining_quantity"] == 5
        assert data["trades"] == []
        assert data["netting_result"] is None

    async def test_ioc_buy_yes_no_resting_asks_cancels(self, client: AsyncClient) -> None:
        """An IOC BUY YES with no matching asks gets immediately CANCELLED."""
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"ioc-miss-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 1,  # extremely low — will never match
                "quantity": 3,
                "time_in_force": "IOC",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        order = data["order"]
        assert order["status"] == "CANCELLED"
        assert order["filled_quantity"] == 0
        assert data["trades"] == []

    async def test_place_order_missing_balance_returns_422(self, client: AsyncClient) -> None:
        """A user with zero balance cannot place a BUY order — InsufficientBalanceError."""
        token = await _register_and_login(client)
        # No deposit — balance is 0
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"no-balance-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 50,
                "quantity": 10,
            },
            headers=headers,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == 2001  # InsufficientBalanceError

    async def test_place_order_invalid_market_returns_422(self, client: AsyncClient) -> None:
        """Placing an order on a non-existent market returns 422 (MarketNotActive check)."""
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"bad-market-{uuid.uuid4().hex[:8]}",
                "market_id": "MKT-DOES-NOT-EXIST",
                "side": "YES",
                "direction": "BUY",
                "price_cents": 50,
                "quantity": 5,
            },
            headers=headers,
        )
        # MarketNotActiveError (3002) or MarketNotFoundError (3001)
        assert resp.status_code in (404, 422)
        assert resp.json()["code"] in (3001, 3002)

    async def test_place_order_price_out_of_range_returns_422(self, client: AsyncClient) -> None:
        """Price must be 1-99; price=100 triggers PriceOutOfRangeError."""
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"oob-price-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 100,  # out of range
                "quantity": 5,
            },
            headers=headers,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == 4001  # PriceOutOfRangeError

    async def test_response_fields_present(self, client: AsyncClient) -> None:
        """Verify all expected fields are present in the place-order response."""
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"fields-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 45,
                "quantity": 2,
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "order" in data
        assert "trades" in data
        assert "netting_result" in data
        order = data["order"]
        for field in ("id", "client_order_id", "market_id", "side", "direction",
                      "price_cents", "quantity", "filled_quantity", "remaining_quantity",
                      "status", "time_in_force"):
            assert field in order, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# TestCancelOrder
# ---------------------------------------------------------------------------


class TestCancelOrder:
    async def test_cancel_order_unfreezes_funds(self, client: AsyncClient) -> None:
        """Cancel a resting GTC buy order — funds should be unfrozen."""
        token = await _register_and_login(client)
        await _fund_user(client, token, 500_000)  # $5,000
        headers = {"Authorization": f"Bearer {token}"}

        # Get balance before placing order
        bal_resp_before = await client.get("/api/v1/account/balance", headers=headers)
        available_before = bal_resp_before.json()["data"]["available_balance_cents"]
        assert available_before == 500_000

        # Place a GTC BUY YES order at price 50, quantity 10 → freezes 50*10 + fee
        order_resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"cancel-test-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 50,
                "quantity": 10,
            },
            headers=headers,
        )
        assert order_resp.status_code == 201
        order_id = order_resp.json()["order"]["id"]

        # Balance should be reduced (funds frozen)
        bal_resp_mid = await client.get("/api/v1/account/balance", headers=headers)
        bal_mid = bal_resp_mid.json()["data"]
        assert bal_mid["available_balance_cents"] < available_before
        assert bal_mid["frozen_balance_cents"] > 0

        # Cancel the order
        cancel_resp = await client.post(
            f"/api/v1/orders/{order_id}/cancel",
            headers=headers,
        )
        assert cancel_resp.status_code == 200
        cancel_data = cancel_resp.json()
        assert cancel_data["order_id"] == order_id
        assert cancel_data["unfrozen_amount"] > 0
        assert cancel_data["unfrozen_asset_type"] == "FUNDS"

        # Balance should be restored to original available amount
        bal_resp_after = await client.get("/api/v1/account/balance", headers=headers)
        bal_after = bal_resp_after.json()["data"]
        assert bal_after["available_balance_cents"] == available_before
        assert bal_after["frozen_balance_cents"] == 0

    async def test_cancelled_order_has_cancelled_status(self, client: AsyncClient) -> None:
        """After cancellation, GET /orders/{id} returns status CANCELLED."""
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}

        place_resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"cancel-status-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 30,
                "quantity": 2,
            },
            headers=headers,
        )
        assert place_resp.status_code == 201
        order_id = place_resp.json()["order"]["id"]

        cancel_resp = await client.post(f"/api/v1/orders/{order_id}/cancel", headers=headers)
        assert cancel_resp.status_code == 200

        get_resp = await client.get(f"/api/v1/orders/{order_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "CANCELLED"

    async def test_cancel_already_cancelled_returns_422(self, client: AsyncClient) -> None:
        """Cancelling an already-cancelled order should return 422."""
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}

        place_resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"double-cancel-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 35,
                "quantity": 1,
            },
            headers=headers,
        )
        assert place_resp.status_code == 201
        order_id = place_resp.json()["order"]["id"]

        # First cancel — success
        first_cancel = await client.post(f"/api/v1/orders/{order_id}/cancel", headers=headers)
        assert first_cancel.status_code == 200

        # Second cancel — order not cancellable
        second_cancel = await client.post(f"/api/v1/orders/{order_id}/cancel", headers=headers)
        assert second_cancel.status_code == 422
        assert second_cancel.json()["code"] == 4006  # OrderNotCancellableError

    async def test_cancel_nonexistent_order_returns_404(self, client: AsyncClient) -> None:
        """Cancelling a non-existent order returns 404."""
        token = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/v1/orders/FAKE-ORDER-ID-999/cancel", headers=headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == 4004  # OrderNotFoundError

    async def test_cancel_another_users_order_returns_403(self, client: AsyncClient) -> None:
        """A user cannot cancel another user's order — returns 403."""
        token_a = await _register_and_login(client)
        token_b = await _register_and_login(client)
        await _fund_user(client, token_a)

        # User A places an order
        place_resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"other-cancel-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 45,
                "quantity": 1,
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert place_resp.status_code == 201
        order_id = place_resp.json()["order"]["id"]

        # User B tries to cancel User A's order
        resp = await client.post(
            f"/api/v1/orders/{order_id}/cancel",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestIdempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    async def test_same_payload_returns_201_with_same_order(self, client: AsyncClient) -> None:
        """Submitting the same client_order_id twice returns 201 with the same order data."""
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}
        coid = f"idempotent-{uuid.uuid4().hex[:8]}"

        payload = {
            "client_order_id": coid,
            "market_id": ACTIVE_MARKET_ID,
            "side": "YES",
            "direction": "BUY",
            "price_cents": 42,
            "quantity": 3,
        }

        resp1 = await client.post("/api/v1/orders", json=payload, headers=headers)
        assert resp1.status_code == 201
        order_id_1 = resp1.json()["order"]["id"]

        resp2 = await client.post("/api/v1/orders", json=payload, headers=headers)
        assert resp2.status_code == 201
        order_id_2 = resp2.json()["order"]["id"]

        # Same order returned — no duplicate created
        assert order_id_1 == order_id_2
        # On idempotent replay, trades list is empty (no re-matching)
        assert resp2.json()["trades"] == []

    async def test_same_coid_different_price_returns_409(self, client: AsyncClient) -> None:
        """Reusing client_order_id with a different price returns 409 (DuplicateOrderError)."""
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}
        coid = f"dup-price-{uuid.uuid4().hex[:8]}"

        # First placement
        resp1 = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": coid,
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 50,
                "quantity": 2,
            },
            headers=headers,
        )
        assert resp1.status_code == 201

        # Second placement with different price — must be rejected
        resp2 = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": coid,
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 55,  # different price
                "quantity": 2,
            },
            headers=headers,
        )
        assert resp2.status_code == 409
        assert resp2.json()["code"] == 4005  # DuplicateOrderError


# ---------------------------------------------------------------------------
# TestMintScenario
# ---------------------------------------------------------------------------


class TestMintScenario:
    async def test_mint_scenario_creates_positions(self, client: AsyncClient) -> None:
        """Full MINT trade: User A BUY YES @65, User B BUY NO @35 → match.

        Transform rules:
          User A: YES BUY @65  → book: NATIVE_BUY,     BUY,  price=65
          User B: NO  BUY @35  → book: SYNTHETIC_SELL, SELL, price=65 (100-35)
        Both hit price 65 → MINT scenario (new YES+NO shares minted).
        User A gets YES shares; User B gets NO shares.
        """
        token_a = await _register_and_login(client)
        token_b = await _register_and_login(client)
        await _fund_user(client, token_a)
        await _fund_user(client, token_b)

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User A: BUY YES @65 (rests in book as NATIVE_BUY BUY @65)
        resp_a = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"mint-a-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 65,
                "quantity": 5,
            },
            headers=headers_a,
        )
        assert resp_a.status_code == 201
        order_a = resp_a.json()["order"]
        assert order_a["status"] == "OPEN"  # resting — no match yet
        assert resp_a.json()["trades"] == []

        # User B: BUY NO @35 → SYNTHETIC_SELL @65 → matches User A's NATIVE_BUY @65
        resp_b = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"mint-b-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "NO",
                "direction": "BUY",
                "price_cents": 35,
                "quantity": 5,
            },
            headers=headers_b,
        )
        assert resp_b.status_code == 201
        data_b = resp_b.json()

        # User B's order should be FILLED (matched User A's entire resting order)
        order_b = data_b["order"]
        assert order_b["status"] == "FILLED"
        assert order_b["filled_quantity"] == 5

        # Exactly one trade should have been produced
        trades = data_b["trades"]
        assert len(trades) == 1
        trade = trades[0]
        assert trade["quantity"] == 5
        assert trade["price"] == 65
        assert trade["scenario"] == "MINT"

        # User A's order must now appear as FILLED via GET /orders/{id}
        get_a = await client.get(f"/api/v1/orders/{order_a['id']}", headers=headers_a)
        assert get_a.status_code == 200
        assert get_a.json()["status"] == "FILLED"
        assert get_a.json()["filled_quantity"] == 5


# ---------------------------------------------------------------------------
# TestListOrders
# ---------------------------------------------------------------------------


class TestListOrders:
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/orders")
        assert resp.status_code == 401

    async def test_new_user_has_empty_order_list(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/orders", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["orders"] == []
        assert data["next_cursor"] is None

    async def test_placed_order_appears_in_list(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}

        await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"list-test-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 40,
                "quantity": 2,
            },
            headers=headers,
        )

        resp = await client.get("/api/v1/orders", headers=headers)
        assert resp.status_code == 200
        orders = resp.json()["orders"]
        assert len(orders) == 1
        assert orders[0]["market_id"] == ACTIVE_MARKET_ID

    async def test_filter_by_market_id(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}

        # Place on two different markets
        for mkt in (ACTIVE_MARKET_ID, "MKT-ETH-10K-2026"):
            await client.post(
                "/api/v1/orders",
                json={
                    "client_order_id": f"multi-mkt-{mkt[-4:]}-{uuid.uuid4().hex[:6]}",
                    "market_id": mkt,
                    "side": "YES",
                    "direction": "BUY",
                    "price_cents": 30,
                    "quantity": 1,
                },
                headers=headers,
            )

        # Filter to only ACTIVE_MARKET_ID
        resp = await client.get(
            f"/api/v1/orders?market_id={ACTIVE_MARKET_ID}", headers=headers
        )
        assert resp.status_code == 200
        orders = resp.json()["orders"]
        assert len(orders) == 1
        assert orders[0]["market_id"] == ACTIVE_MARKET_ID

    async def test_filter_by_status_open(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}

        # Place a GTC order (will remain OPEN)
        place_resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"status-filter-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 20,
                "quantity": 1,
            },
            headers=headers,
        )
        assert place_resp.status_code == 201

        resp = await client.get("/api/v1/orders?status=OPEN", headers=headers)
        assert resp.status_code == 200
        orders = resp.json()["orders"]
        assert all(o["status"] == "OPEN" for o in orders)


# ---------------------------------------------------------------------------
# TestGetOrder
# ---------------------------------------------------------------------------


class TestGetOrder:
    async def test_get_own_order(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        await _fund_user(client, token)
        headers = {"Authorization": f"Bearer {token}"}

        place_resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"get-order-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 55,
                "quantity": 1,
            },
            headers=headers,
        )
        assert place_resp.status_code == 201
        order_id = place_resp.json()["order"]["id"]

        resp = await client.get(f"/api/v1/orders/{order_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == order_id
        assert data["market_id"] == ACTIVE_MARKET_ID

    async def test_get_nonexistent_order_returns_404(self, client: AsyncClient) -> None:
        token = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/orders/ORDER-DOES-NOT-EXIST", headers=headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == 4004

    async def test_get_other_users_order_returns_403(self, client: AsyncClient) -> None:
        token_a = await _register_and_login(client)
        token_b = await _register_and_login(client)
        await _fund_user(client, token_a)

        place_resp = await client.post(
            "/api/v1/orders",
            json={
                "client_order_id": f"get-other-{uuid.uuid4().hex[:8]}",
                "market_id": ACTIVE_MARKET_ID,
                "side": "YES",
                "direction": "BUY",
                "price_cents": 60,
                "quantity": 1,
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert place_resp.status_code == 201
        order_id = place_resp.json()["order"]["id"]

        resp = await client.get(
            f"/api/v1/orders/{order_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 403
