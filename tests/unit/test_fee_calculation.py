from src.pm_clearing.domain.fee import calc_fee, get_fee_trade_value


class TestGetFeeTradeValue:
    def test_native_buy_uses_yes_price(self) -> None:
        # NATIVE_BUY @ YES price 65, qty 100
        assert get_fee_trade_value("NATIVE_BUY", 65, 100, 0) == 65 * 100

    def test_native_sell_uses_yes_price(self) -> None:
        assert get_fee_trade_value("NATIVE_SELL", 65, 100, 0) == 65 * 100

    def test_synthetic_sell_uses_no_price(self) -> None:
        # Buy NO @35 → SYNTHETIC_SELL, YES trade price=65, NO original_price=35
        assert get_fee_trade_value("SYNTHETIC_SELL", 65, 100, 35) == 35 * 100

    def test_synthetic_buy_uses_no_price(self) -> None:
        # Sell NO @40 → SYNTHETIC_BUY, YES trade price=60, NO price = 100-60=40
        assert get_fee_trade_value("SYNTHETIC_BUY", 60, 100, 0) == 40 * 100


class TestCalcFee:
    def test_ceiling_division(self) -> None:
        # fee = (100 * 20 + 9999) // 10000 = 10119 // 10000 = 1
        assert calc_fee(100, 20) == 1

    def test_exact_division(self) -> None:
        # fee = (10000 * 20 + 9999) // 10000 = 209999 // 10000 = 20
        assert calc_fee(10000, 20) == 20

    def test_large_value(self) -> None:
        # 6500 cents * 20 bps ceiling
        assert calc_fee(6500, 20) == (6500 * 20 + 9999) // 10000
