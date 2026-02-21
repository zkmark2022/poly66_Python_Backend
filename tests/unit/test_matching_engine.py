"""Unit tests for MatchingEngine orchestrator."""
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.pm_matching.engine.engine import MatchingEngine, _sync_frozen_amount
from src.pm_order.domain.models import Order


def _make_order(**kwargs: Any) -> Order:
    defaults: dict[str, Any] = {
        "id": "order-1",
        "client_order_id": "client-1",
        "market_id": "mkt-1",
        "user_id": "user-1",
        "original_side": "YES",
        "original_direction": "BUY",
        "original_price": 65,
        "book_type": "NATIVE_BUY",
        "book_direction": "BUY",
        "book_price": 65,
        "quantity": 100,
        "frozen_amount": 6700,
        "frozen_asset_type": "FUNDS",
        "time_in_force": "GTC",
        "status": "OPEN",
    }
    defaults.update(kwargs)
    return Order(**defaults)


@pytest.fixture
def engine() -> MatchingEngine:
    return MatchingEngine()


class TestMatchingEngineInit:
    def test_engine_starts_empty(self, engine: MatchingEngine) -> None:
        assert len(engine._orderbooks) == 0
        assert len(engine._market_locks) == 0

    def test_get_or_create_orderbook(self, engine: MatchingEngine) -> None:
        ob1 = engine._get_or_create_orderbook("mkt-1")
        ob2 = engine._get_or_create_orderbook("mkt-1")
        assert ob1 is ob2  # same instance returned
        assert len(engine._orderbooks) == 1

    def test_get_or_create_orderbook_different_markets(self, engine: MatchingEngine) -> None:
        ob1 = engine._get_or_create_orderbook("mkt-1")
        ob2 = engine._get_or_create_orderbook("mkt-2")
        assert ob1 is not ob2
        assert len(engine._orderbooks) == 2


class TestSyncFrozenAmount:
    def test_native_buy_funds(self) -> None:
        order = _make_order(
            book_type="NATIVE_BUY", book_price=65, original_price=65, frozen_asset_type="FUNDS"
        )
        _sync_frozen_amount(order, 50)
        # remaining_value = 65 * 50 = 3250; fee = ceil(3250 * 20 / 10000) = ceil(6.5) = 7
        expected = 3250 + 7
        assert order.frozen_amount == expected

    def test_synthetic_sell_uses_original_price(self) -> None:
        order = _make_order(
            book_type="SYNTHETIC_SELL", book_price=35, original_price=65, frozen_asset_type="FUNDS"
        )
        _sync_frozen_amount(order, 50)
        remaining_value = 65 * 50  # original_price used for SYNTHETIC_SELL
        fee = (remaining_value * 20 + 9999) // 10000
        assert order.frozen_amount == remaining_value + fee

    def test_yes_shares_frozen(self) -> None:
        order = _make_order(book_type="NATIVE_SELL", frozen_asset_type="YES_SHARES")
        _sync_frozen_amount(order, 30)
        assert order.frozen_amount == 30

    def test_no_shares_frozen(self) -> None:
        order = _make_order(book_type="SYNTHETIC_BUY", frozen_asset_type="NO_SHARES")
        _sync_frozen_amount(order, 15)
        assert order.frozen_amount == 15

    def test_zero_remaining(self) -> None:
        order = _make_order(
            book_type="NATIVE_BUY", book_price=65, original_price=65, frozen_asset_type="FUNDS"
        )
        _sync_frozen_amount(order, 0)
        assert order.frozen_amount == 0


class TestCancelOrderValidation:
    async def test_cancel_order_not_found_raises_4004(self, engine: MatchingEngine) -> None:
        repo = AsyncMock()
        repo.get_by_id.return_value = None
        db = AsyncMock()
        from src.pm_common.errors import AppError
        with pytest.raises(AppError) as exc:
            await engine.cancel_order("missing-id", "user-1", repo, db)
        assert exc.value.code == 4004

    async def test_cancel_order_wrong_user_raises_403(self, engine: MatchingEngine) -> None:
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(user_id="other-user", status="OPEN")
        db = AsyncMock()
        from src.pm_common.errors import AppError
        with pytest.raises(AppError) as exc:
            await engine.cancel_order("order-1", "user-1", repo, db)
        assert exc.value.code == 403

    async def test_cancel_order_non_cancellable_raises_4006(self, engine: MatchingEngine) -> None:
        repo = AsyncMock()
        repo.get_by_id.return_value = _make_order(user_id="user-1", status="FILLED")
        db = AsyncMock()
        from src.pm_common.errors import AppError
        with pytest.raises(AppError) as exc:
            await engine.cancel_order("order-1", "user-1", repo, db)
        assert exc.value.code == 4006
