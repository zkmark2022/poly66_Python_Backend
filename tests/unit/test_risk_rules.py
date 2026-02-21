import pytest

from src.pm_common.errors import AppError
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
