from datetime import UTC, datetime

from src.pm_market.application.schemas import (
    MarketDetail,
    MarketListItem,
    OrderbookResponse,
    cursor_decode,
    cursor_encode,
)
from src.pm_market.domain.models import Market, OrderbookSnapshot, PriceLevel


def _make_market(**kwargs) -> Market:
    defaults = dict(
        id="MKT-TEST",
        title="Test Market",
        description="A test market",
        category="crypto",
        status="ACTIVE",
        min_price_cents=1,
        max_price_cents=99,
        max_order_quantity=10000,
        max_position_per_user=25000,
        max_order_amount_cents=1000000,
        maker_fee_bps=10,
        taker_fee_bps=20,
        reserve_balance=500000,
        pnl_pool=-1200,
        total_yes_shares=5000,
        total_no_shares=5000,
        trading_start_at=None,
        trading_end_at=None,
        resolution_date=None,
        resolved_at=None,
        settled_at=None,
        resolution_result=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    defaults.update(kwargs)
    return Market(**defaults)


class TestCursorEncodeDecode:
    def test_roundtrip(self):
        m = _make_market(id="MKT-BTC", created_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC))
        encoded = cursor_encode(m)
        ts, mid = cursor_decode(encoded)
        assert mid == "MKT-BTC"
        assert ts is not None
        assert ts == "2026-01-15T12:00:00+00:00"

    def test_decode_none_returns_none(self):
        ts, mid = cursor_decode(None)
        assert ts is None
        assert mid is None

    def test_decode_invalid_returns_none(self):
        ts, mid = cursor_decode("not-valid-base64!!")
        assert ts is None
        assert mid is None


class TestMarketListItem:
    def test_from_domain_basic_fields(self):
        m = _make_market(reserve_balance=500000)
        item = MarketListItem.from_domain(m)
        assert item.id == "MKT-TEST"
        assert item.status == "ACTIVE"
        assert item.reserve_balance_cents == 500000
        assert item.reserve_balance_display == "$5,000.00"

    def test_from_domain_null_timestamps(self):
        m = _make_market(trading_start_at=None, resolution_date=None)
        item = MarketListItem.from_domain(m)
        assert item.trading_start_at is None
        assert item.resolution_date is None


class TestMarketDetail:
    def test_from_domain_includes_pnl_pool(self):
        m = _make_market(pnl_pool=-1200)
        detail = MarketDetail.from_domain(m)
        assert detail.pnl_pool_cents == -1200
        assert detail.pnl_pool_display == "-$12.00"

    def test_from_domain_includes_risk_params(self):
        m = _make_market()
        detail = MarketDetail.from_domain(m)
        assert detail.max_order_quantity == 10000
        assert detail.max_position_per_user == 25000
        assert detail.max_order_amount_cents == 1000000


class TestOrderbookResponse:
    def _make_snapshot(self) -> OrderbookSnapshot:
        return OrderbookSnapshot(
            market_id="MKT-TEST",
            yes_bids=[PriceLevel(65, 500), PriceLevel(64, 300)],
            yes_asks=[PriceLevel(67, 400), PriceLevel(68, 200)],
            last_trade_price_cents=65,
            updated_at=datetime.now(UTC),
        )

    def test_yes_side_preserved(self):
        resp = OrderbookResponse.from_snapshot(self._make_snapshot())
        assert resp.yes.bids[0].price_cents == 65
        assert resp.yes.asks[0].price_cents == 67

    def test_no_bids_from_yes_asks(self):
        """NO bids = 100 - YES asks, sorted descending."""
        resp = OrderbookResponse.from_snapshot(self._make_snapshot())
        # YES asks: [67, 68] → NO bids: [100-67=33, 100-68=32], sorted desc → [33, 32]
        assert resp.no.bids[0].price_cents == 33   # 100 - 67
        assert resp.no.bids[1].price_cents == 32   # 100 - 68

    def test_no_asks_from_yes_bids(self):
        """NO asks = 100 - YES bids, sorted ascending."""
        resp = OrderbookResponse.from_snapshot(self._make_snapshot())
        # YES bids: [65, 64] → NO asks: [100-65=35, 100-64=36], sorted asc → [35, 36]
        assert resp.no.asks[0].price_cents == 35   # 100 - 65
        assert resp.no.asks[1].price_cents == 36   # 100 - 64

    def test_no_quantities_match(self):
        """NO quantities mirror YES quantities."""
        resp = OrderbookResponse.from_snapshot(self._make_snapshot())
        yes_ask_total = sum(lv.total_quantity for lv in self._make_snapshot().yes_asks)
        no_bid_total = sum(lv.total_quantity for lv in resp.no.bids)
        assert yes_ask_total == no_bid_total

    def test_empty_orderbook(self):
        snap = OrderbookSnapshot(
            market_id="MKT-EMPTY",
            yes_bids=[],
            yes_asks=[],
            last_trade_price_cents=None,
            updated_at=datetime.now(UTC),
        )
        resp = OrderbookResponse.from_snapshot(snap)
        assert resp.yes.bids == []
        assert resp.no.bids == []
        assert resp.last_trade_price_cents is None
