# tests/unit/test_market_domain_models.py
from datetime import UTC, datetime

from src.pm_market.domain.models import Market, OrderbookSnapshot, PriceLevel


def _make_market(**kwargs) -> Market:
    defaults = dict(
        id="MKT-TEST",
        title="Test Market",
        description=None,
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
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    return Market(**defaults)


class TestMarket:
    def test_construction(self):
        m = _make_market()
        assert m.id == "MKT-TEST"
        assert m.status == "ACTIVE"
        assert m.pnl_pool == -1200   # can be negative

    def test_optional_fields_none(self):
        m = _make_market()
        assert m.description is None
        assert m.resolution_result is None
        assert m.resolved_at is None


class TestPriceLevel:
    def test_construction(self):
        lv = PriceLevel(price_cents=65, total_quantity=500)
        assert lv.price_cents == 65
        assert lv.total_quantity == 500


class TestOrderbookSnapshot:
    def test_construction(self):
        snap = OrderbookSnapshot(
            market_id="MKT-TEST",
            yes_bids=[PriceLevel(65, 500), PriceLevel(64, 300)],
            yes_asks=[PriceLevel(67, 400)],
            last_trade_price_cents=65,
            updated_at=datetime.now(UTC),
        )
        assert snap.market_id == "MKT-TEST"
        assert len(snap.yes_bids) == 2
        assert snap.last_trade_price_cents == 65

    def test_empty_orderbook(self):
        snap = OrderbookSnapshot(
            market_id="MKT-EMPTY",
            yes_bids=[],
            yes_asks=[],
            last_trade_price_cents=None,
            updated_at=datetime.now(UTC),
        )
        assert snap.yes_bids == []
        assert snap.last_trade_price_cents is None
