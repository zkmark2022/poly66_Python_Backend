# tests/unit/test_market_service.py
"""Unit tests for MarketApplicationService using mock repository."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pm_common.errors import MarketNotActiveError, MarketNotFoundError
from src.pm_market.application.service import MarketApplicationService
from src.pm_market.domain.models import Market, OrderbookSnapshot


def _make_market(**kwargs) -> Market:
    defaults = dict(
        id="MKT-TEST", title="Test", description=None, category="crypto",
        status="ACTIVE", min_price_cents=1, max_price_cents=99,
        max_order_quantity=10000, max_position_per_user=25000,
        max_order_amount_cents=1000000, maker_fee_bps=10, taker_fee_bps=20,
        reserve_balance=0, pnl_pool=0, total_yes_shares=0, total_no_shares=0,
        trading_start_at=None, trading_end_at=None, resolution_date=None,
        resolved_at=None, settled_at=None, resolution_result=None,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    return Market(**defaults)


def _make_snapshot(market_id: str = "MKT-TEST") -> OrderbookSnapshot:
    return OrderbookSnapshot(
        market_id=market_id, yes_bids=[], yes_asks=[],
        last_trade_price_cents=None, updated_at=datetime.now(UTC)
    )


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def mock_repo():
    return MagicMock()


class TestListMarkets:
    @pytest.mark.asyncio
    async def test_returns_list_response(self, db, mock_repo):
        markets = [_make_market(id=f"MKT-{i}") for i in range(3)]
        mock_repo.list_markets = AsyncMock(return_value=markets)
        svc = MarketApplicationService(repo=mock_repo)

        resp = await svc.list_markets(db, status=None, category=None, cursor=None, limit=20)

        assert len(resp.items) == 3
        assert resp.has_more is False
        assert resp.next_cursor is None

    @pytest.mark.asyncio
    async def test_has_more_when_over_limit(self, db, mock_repo):
        # repo returns limit+1 items → has_more=True
        markets = [_make_market(id=f"MKT-{i}") for i in range(21)]
        mock_repo.list_markets = AsyncMock(return_value=markets)
        svc = MarketApplicationService(repo=mock_repo)

        resp = await svc.list_markets(db, status=None, category=None, cursor=None, limit=20)

        assert resp.has_more is True
        assert len(resp.items) == 20
        assert resp.next_cursor is not None

    @pytest.mark.asyncio
    async def test_status_all_passes_none_to_repo(self, db, mock_repo):
        mock_repo.list_markets = AsyncMock(return_value=[])
        svc = MarketApplicationService(repo=mock_repo)

        await svc.list_markets(db, status="ALL", category=None, cursor=None, limit=20)

        call_args = mock_repo.list_markets.call_args
        assert call_args.args[1] is None  # status=None passed to repo


class TestGetMarket:
    @pytest.mark.asyncio
    async def test_returns_detail_when_found(self, db, mock_repo):
        mock_repo.get_market_by_id = AsyncMock(return_value=_make_market(id="MKT-BTC"))
        svc = MarketApplicationService(repo=mock_repo)

        detail = await svc.get_market(db, "MKT-BTC")

        assert detail.id == "MKT-BTC"

    @pytest.mark.asyncio
    async def test_raises_not_found(self, db, mock_repo):
        mock_repo.get_market_by_id = AsyncMock(return_value=None)
        svc = MarketApplicationService(repo=mock_repo)

        with pytest.raises(MarketNotFoundError):
            await svc.get_market(db, "MKT-MISSING")


class TestGetOrderbook:
    @pytest.mark.asyncio
    async def test_returns_orderbook_response(self, db, mock_repo):
        mock_repo.get_market_by_id = AsyncMock(
            return_value=_make_market(id="MKT-BTC", status="ACTIVE")
        )
        mock_repo.get_orderbook_snapshot = AsyncMock(
            return_value=_make_snapshot("MKT-BTC")
        )
        svc = MarketApplicationService(repo=mock_repo)

        resp = await svc.get_orderbook(db, "MKT-BTC", levels=10)

        assert resp.market_id == "MKT-BTC"
        assert resp.yes.bids == []

    @pytest.mark.asyncio
    async def test_raises_not_found(self, db, mock_repo):
        mock_repo.get_market_by_id = AsyncMock(return_value=None)
        svc = MarketApplicationService(repo=mock_repo)

        with pytest.raises(MarketNotFoundError):
            await svc.get_orderbook(db, "MKT-MISSING", levels=10)

    @pytest.mark.asyncio
    async def test_raises_not_active_for_non_active_market(self, db, mock_repo):
        mock_repo.get_market_by_id = AsyncMock(
            return_value=_make_market(id="MKT-SETTLED", status="SETTLED")
        )
        svc = MarketApplicationService(repo=mock_repo)

        with pytest.raises(MarketNotActiveError):
            await svc.get_orderbook(db, "MKT-SETTLED", levels=10)
