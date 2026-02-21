# tests/unit/test_market_persistence.py
"""Unit tests for MarketRepository using MagicMock AsyncSession."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pm_market.infrastructure.persistence import MarketRepository


def _make_market_row(**kwargs):
    """Build a mock DB row with all required fields."""
    row = MagicMock()
    row.id = kwargs.get("id", "MKT-TEST")
    row.title = kwargs.get("title", "Test Market")
    row.description = kwargs.get("description")
    row.category = kwargs.get("category", "crypto")
    row.status = kwargs.get("status", "ACTIVE")
    row.min_price_cents = 1
    row.max_price_cents = 99
    row.max_order_quantity = 10000
    row.max_position_per_user = 25000
    row.max_order_amount_cents = 1000000
    row.maker_fee_bps = 10
    row.taker_fee_bps = 20
    row.reserve_balance = 500000
    row.pnl_pool = 0
    row.total_yes_shares = 5000
    row.total_no_shares = 5000
    row.trading_start_at = None
    row.trading_end_at = None
    row.resolution_date = None
    row.resolved_at = None
    row.settled_at = None
    row.resolution_result = None
    row.created_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    return row


@pytest.fixture
def db():
    return MagicMock()


class TestGetMarketById:
    @pytest.mark.asyncio
    async def test_returns_market_when_found(self, db):
        row = _make_market_row(id="MKT-BTC", title="BTC Market")
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        db.execute = AsyncMock(return_value=result_mock)

        repo = MarketRepository()
        market = await repo.get_market_by_id(db, "MKT-BTC")

        assert market is not None
        assert market.id == "MKT-BTC"
        assert market.title == "BTC Market"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, db):
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        repo = MarketRepository()
        market = await repo.get_market_by_id(db, "MKT-MISSING")

        assert market is None


class TestListMarkets:
    @pytest.mark.asyncio
    async def test_returns_list(self, db):
        rows = [_make_market_row(id=f"MKT-{i}") for i in range(3)]
        result_mock = MagicMock()
        result_mock.fetchall.return_value = rows
        db.execute = AsyncMock(return_value=result_mock)

        repo = MarketRepository()
        markets = await repo.list_markets(db, "ACTIVE", None, None, None, 20)

        assert len(markets) == 3

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, db):
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        repo = MarketRepository()
        markets = await repo.list_markets(db, "ACTIVE", None, None, None, 20)

        assert markets == []
