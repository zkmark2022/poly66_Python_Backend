from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pm_common.errors import AppError
from src.pm_order.domain.models import Order
from src.pm_risk.rules.balance_check import TAKER_FEE_BPS, check_and_freeze
from src.pm_risk.rules.market_status import check_market_active
from src.pm_risk.rules.order_limit import MAX_ORDER_QUANTITY, check_order_limit
from src.pm_risk.rules.price_range import check_price_range
from src.pm_risk.rules.self_trade import is_self_trade


class TestPriceRange:
    def test_valid_price(self) -> None:
        check_price_range(50)  # no exception

    def test_boundary_low(self) -> None:
        check_price_range(1)

    def test_boundary_high(self) -> None:
        check_price_range(99)

    def test_price_zero_raises(self) -> None:
        with pytest.raises(AppError) as exc_info:
            check_price_range(0)
        assert exc_info.value.code == 4001

    def test_price_100_raises(self) -> None:
        with pytest.raises(AppError) as exc_info:
            check_price_range(100)
        assert exc_info.value.code == 4001


class TestOrderLimit:
    def test_valid_quantity(self) -> None:
        check_order_limit(1000)

    def test_max_quantity(self) -> None:
        check_order_limit(MAX_ORDER_QUANTITY)

    def test_exceeds_limit_raises(self) -> None:
        with pytest.raises(AppError) as exc_info:
            check_order_limit(MAX_ORDER_QUANTITY + 1)
        assert exc_info.value.code == 4002

    def test_zero_raises(self) -> None:
        with pytest.raises(AppError) as exc_info:
            check_order_limit(0)
        assert exc_info.value.code == 4002


class TestSelfTrade:
    def test_same_user_is_self_trade(self) -> None:
        assert is_self_trade("user-A", "user-A") is True

    def test_different_user_is_not(self) -> None:
        assert is_self_trade("user-A", "user-B") is False


def _make_order(**kwargs: object) -> Order:
    defaults: dict[str, object] = dict(
        id="01ARZ", client_order_id="c1", market_id="mkt-1", user_id="u1",
        original_side="YES", original_direction="BUY", original_price=65,
        book_type="NATIVE_BUY", book_direction="BUY", book_price=65,
        quantity=100, frozen_amount=0, frozen_asset_type="", time_in_force="GTC", status="OPEN",
    )
    defaults.update(kwargs)
    return Order(**defaults)  # type: ignore[arg-type]


def _db_returning_scalar(scalar_value: object) -> AsyncMock:
    """Return an AsyncMock db where execute().scalar_one_or_none() == scalar_value."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_value
    mock_db.execute.return_value = mock_result
    return mock_db


def _db_returning_fetchone(row: object) -> AsyncMock:
    """Return an AsyncMock db where execute().fetchone() == row."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = row
    mock_db.execute.return_value = mock_result
    return mock_db


class TestMarketStatus:
    async def test_active_market_ok(self) -> None:
        mock_db = _db_returning_scalar("ACTIVE")
        await check_market_active("mkt-1", mock_db)  # no exception

    async def test_suspended_market_raises_3002(self) -> None:
        mock_db = _db_returning_scalar("SUSPENDED")
        with pytest.raises(AppError) as exc_info:
            await check_market_active("mkt-1", mock_db)
        assert exc_info.value.code == 3002

    async def test_missing_market_raises_3001(self) -> None:
        mock_db = _db_returning_scalar(None)
        with pytest.raises(AppError) as exc_info:
            await check_market_active("mkt-1", mock_db)
        assert exc_info.value.code == 3001


class TestBalanceCheck:
    async def test_native_buy_freeze_sets_frozen_amount_with_fee_buffer(self) -> None:
        order = _make_order(book_type="NATIVE_BUY", original_price=65, quantity=100)
        mock_db = _db_returning_fetchone(("row",))
        await check_and_freeze(order, mock_db)
        trade_value = 65 * 100  # 6500
        expected_fee = (trade_value * TAKER_FEE_BPS + 9999) // 10000  # 13
        assert order.frozen_amount == trade_value + expected_fee
        assert order.frozen_asset_type == "FUNDS"

    async def test_synthetic_sell_uses_original_no_price(self) -> None:
        # Buy NO @35 → SYNTHETIC_SELL, freeze based on NO price 35
        order = _make_order(
            book_type="SYNTHETIC_SELL", original_price=35, book_price=65, quantity=100
        )
        mock_db = _db_returning_fetchone(("row",))
        await check_and_freeze(order, mock_db)
        trade_value = 35 * 100  # NO price
        expected_fee = (trade_value * TAKER_FEE_BPS + 9999) // 10000
        assert order.frozen_amount == trade_value + expected_fee
        assert order.frozen_asset_type == "FUNDS"

    async def test_funds_insufficient_raises_2001(self) -> None:
        order = _make_order(book_type="NATIVE_BUY", original_price=65, quantity=100)
        mock_db = _db_returning_fetchone(None)
        with pytest.raises(AppError) as exc_info:
            await check_and_freeze(order, mock_db)
        assert exc_info.value.code == 2001

    async def test_native_sell_freezes_yes_shares(self) -> None:
        order = _make_order(book_type="NATIVE_SELL", quantity=50)
        mock_db = _db_returning_fetchone(("row",))
        await check_and_freeze(order, mock_db)
        assert order.frozen_amount == 50
        assert order.frozen_asset_type == "YES_SHARES"

    async def test_synthetic_buy_freezes_no_shares(self) -> None:
        order = _make_order(book_type="SYNTHETIC_BUY", quantity=80)
        mock_db = _db_returning_fetchone(("row",))
        await check_and_freeze(order, mock_db)
        assert order.frozen_amount == 80
        assert order.frozen_asset_type == "NO_SHARES"
