# tests/integration/test_market_flow.py
"""Integration tests for pm_market endpoints.

Requires Docker (make up) + migrations (make migrate).
Seed data: 3 ACTIVE markets from 011_seed_initial_data.py.
  - MKT-BTC-100K-2026 (category: crypto)
  - MKT-ETH-10K-2026 (category: crypto)
  - MKT-FED-RATE-CUT-2026Q2 (category: economics)
"""

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


class TestUnauthenticated:
    async def test_list_markets_requires_auth(self, client):
        resp = await client.get("/api/v1/markets")
        assert resp.status_code == 401

    async def test_get_market_requires_auth(self, client):
        resp = await client.get("/api/v1/markets/MKT-BTC-100K-2026")
        assert resp.status_code == 401

    async def test_orderbook_requires_auth(self, client):
        resp = await client.get("/api/v1/markets/MKT-BTC-100K-2026/orderbook")
        assert resp.status_code == 401


class TestListMarkets:
    async def test_default_returns_active_markets(self, auth_client):
        resp = await auth_client.get("/api/v1/markets")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 3
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    async def test_status_filter_active(self, auth_client):
        resp = await auth_client.get("/api/v1/markets?status=ACTIVE")
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert all(i["status"] == "ACTIVE" for i in items)

    async def test_category_filter_crypto(self, auth_client):
        resp = await auth_client.get("/api/v1/markets?category=crypto")
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 2
        assert all(i["category"] == "crypto" for i in items)

    async def test_status_all_returns_all(self, auth_client):
        resp = await auth_client.get("/api/v1/markets?status=ALL")
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 3

    async def test_cursor_pagination(self, auth_client):
        # Page 1: limit=2
        resp1 = await auth_client.get("/api/v1/markets?limit=2")
        assert resp1.status_code == 200
        data1 = resp1.json()["data"]
        assert len(data1["items"]) == 2
        assert data1["has_more"] is True
        assert data1["next_cursor"] is not None

        # Page 2: use cursor
        cursor = data1["next_cursor"]
        resp2 = await auth_client.get(f"/api/v1/markets?limit=2&cursor={cursor}")
        assert resp2.status_code == 200
        data2 = resp2.json()["data"]
        assert len(data2["items"]) == 1
        assert data2["has_more"] is False

        # No overlap between pages
        ids1 = {i["id"] for i in data1["items"]}
        ids2 = {i["id"] for i in data2["items"]}
        assert ids1.isdisjoint(ids2)

    async def test_list_response_fields(self, auth_client):
        resp = await auth_client.get("/api/v1/markets")
        item = resp.json()["data"]["items"][0]
        # Required fields present
        assert "id" in item
        assert "title" in item
        assert "status" in item
        assert "reserve_balance_cents" in item
        assert "reserve_balance_display" in item
        # Not in list item (lightweight schema)
        assert "pnl_pool_cents" not in item
        assert "max_order_quantity" not in item


class TestGetMarket:
    async def test_returns_full_detail(self, auth_client):
        resp = await auth_client.get("/api/v1/markets/MKT-BTC-100K-2026")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "MKT-BTC-100K-2026"
        # Full detail fields
        assert "pnl_pool_cents" in data
        assert "pnl_pool_display" in data
        assert "max_order_quantity" in data
        assert "max_position_per_user" in data
        assert "max_order_amount_cents" in data

    async def test_not_found_returns_404(self, auth_client):
        resp = await auth_client.get("/api/v1/markets/MKT-DOES-NOT-EXIST")
        assert resp.status_code == 404
        assert resp.json()["code"] == 3001

    async def test_reserve_balance_display_format(self, auth_client):
        resp = await auth_client.get("/api/v1/markets/MKT-BTC-100K-2026")
        data = resp.json()["data"]
        # reserve_balance=0 from seed → $0.00
        assert data["reserve_balance_display"] == "$0.00"


class TestGetOrderbook:
    async def test_empty_orderbook_returns_empty_lists(self, auth_client):
        """No orders exist yet (Module 5 not done), so all lists are empty."""
        resp = await auth_client.get("/api/v1/markets/MKT-BTC-100K-2026/orderbook")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["market_id"] == "MKT-BTC-100K-2026"
        assert data["yes"]["bids"] == []
        assert data["yes"]["asks"] == []
        assert data["no"]["bids"] == []
        assert data["no"]["asks"] == []
        assert data["last_trade_price_cents"] is None

    async def test_orderbook_not_found_returns_404(self, auth_client):
        resp = await auth_client.get("/api/v1/markets/MKT-MISSING/orderbook")
        assert resp.status_code == 404
        assert resp.json()["code"] == 3001

    async def test_levels_param_accepted(self, auth_client):
        resp = await auth_client.get("/api/v1/markets/MKT-BTC-100K-2026/orderbook?levels=5")
        assert resp.status_code == 200

    async def test_response_has_dual_view_structure(self, auth_client):
        resp = await auth_client.get("/api/v1/markets/MKT-BTC-100K-2026/orderbook")
        data = resp.json()["data"]
        assert "yes" in data
        assert "no" in data
        assert "bids" in data["yes"]
        assert "asks" in data["yes"]
        assert "bids" in data["no"]
        assert "asks" in data["no"]
