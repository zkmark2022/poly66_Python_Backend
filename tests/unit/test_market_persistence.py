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


class TestGetOrderbookSnapshot:
    def _make_order_row(self, book_price: int, book_direction: str, total_qty: int):
        row = MagicMock()
        row.book_price = book_price
        row.book_direction = book_direction
        row.total_qty = total_qty
        return row

    def _make_trade_row(self, price: int):
        row = MagicMock()
        row.price = price
        return row

    def _mock_db(self, order_rows, trade_row):
        """Return a db mock with two execute calls: orders then trade."""
        db = MagicMock()
        order_result = MagicMock()
        order_result.fetchall.return_value = order_rows
        trade_result = MagicMock()
        trade_result.fetchone.return_value = trade_row

        db.execute = AsyncMock(side_effect=[order_result, trade_result])
        return db

    @pytest.mark.asyncio
    async def test_classifies_buy_as_bid_sell_as_ask(self):
        order_rows = [
            self._make_order_row(book_price=65, book_direction="BUY", total_qty=500),
            self._make_order_row(book_price=67, book_direction="SELL", total_qty=400),
        ]
        db = self._mock_db(order_rows, trade_row=self._make_trade_row(65))
        repo = MarketRepository()

        snap = await repo.get_orderbook_snapshot(db, "MKT-TEST", levels=10)

        assert len(snap.yes_bids) == 1
        assert snap.yes_bids[0].price_cents == 65
        assert len(snap.yes_asks) == 1
        assert snap.yes_asks[0].price_cents == 67

    @pytest.mark.asyncio
    async def test_bids_sorted_descending_asks_sorted_ascending(self):
        order_rows = [
            self._make_order_row(book_price=62, book_direction="BUY", total_qty=100),
            self._make_order_row(book_price=65, book_direction="BUY", total_qty=300),
            self._make_order_row(book_price=64, book_direction="BUY", total_qty=200),
            self._make_order_row(book_price=68, book_direction="SELL", total_qty=150),
            self._make_order_row(book_price=66, book_direction="SELL", total_qty=250),
        ]
        db = self._mock_db(order_rows, trade_row=None)
        repo = MarketRepository()

        snap = await repo.get_orderbook_snapshot(db, "MKT-TEST", levels=10)

        # Bids should be descending
        bid_prices = [lv.price_cents for lv in snap.yes_bids]
        assert bid_prices == sorted(bid_prices, reverse=True)
        assert bid_prices == [65, 64, 62]

        # Asks should be ascending
        ask_prices = [lv.price_cents for lv in snap.yes_asks]
        assert ask_prices == sorted(ask_prices)
        assert ask_prices == [66, 68]

    @pytest.mark.asyncio
    async def test_levels_truncation(self):
        """Only top `levels` bids and asks are returned."""
        order_rows = [
            self._make_order_row(book_price=i, book_direction="BUY", total_qty=100)
            for i in range(1, 6)  # 5 BUY rows at prices 1..5
        ] + [
            self._make_order_row(book_price=i, book_direction="SELL", total_qty=100)
            for i in range(6, 11)  # 5 SELL rows at prices 6..10
        ]
        db = self._mock_db(order_rows, trade_row=None)
        repo = MarketRepository()

        snap = await repo.get_orderbook_snapshot(db, "MKT-TEST", levels=2)

        # Only top 2 bids (highest prices): 5, 4
        assert len(snap.yes_bids) == 2
        assert snap.yes_bids[0].price_cents == 5
        assert snap.yes_bids[1].price_cents == 4

        # Only top 2 asks (lowest prices): 6, 7
        assert len(snap.yes_asks) == 2
        assert snap.yes_asks[0].price_cents == 6
        assert snap.yes_asks[1].price_cents == 7

    @pytest.mark.asyncio
    async def test_last_trade_price_from_trade_row(self):
        db = self._mock_db([], trade_row=self._make_trade_row(65))
        repo = MarketRepository()

        snap = await repo.get_orderbook_snapshot(db, "MKT-TEST", levels=10)

        assert snap.last_trade_price_cents == 65

    @pytest.mark.asyncio
    async def test_last_trade_price_none_when_no_trades(self):
        db = self._mock_db([], trade_row=None)
        repo = MarketRepository()

        snap = await repo.get_orderbook_snapshot(db, "MKT-TEST", levels=10)

        assert snap.last_trade_price_cents is None

    @pytest.mark.asyncio
    async def test_empty_orders_returns_empty_snapshot(self):
        db = self._mock_db([], trade_row=None)
        repo = MarketRepository()

        snap = await repo.get_orderbook_snapshot(db, "MKT-TEST", levels=10)

        assert snap.yes_bids == []
        assert snap.yes_asks == []
        assert snap.market_id == "MKT-TEST"
