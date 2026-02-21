"""Tests for pm_common.cents — integer arithmetic utilities."""

import pytest

from src.pm_common.cents import calculate_fee, cents_to_display, validate_price


class TestValidatePrice:
    def test_valid_prices(self) -> None:
        for p in [1, 50, 99]:
            validate_price(p)  # Should not raise

    def test_boundary_low(self) -> None:
        validate_price(1)  # OK

    def test_boundary_high(self) -> None:
        validate_price(99)  # OK

    def test_zero_raises(self) -> None:
        with pytest.raises(ValueError, match=r"1.*99"):
            validate_price(0)

    def test_hundred_raises(self) -> None:
        with pytest.raises(ValueError, match=r"1.*99"):
            validate_price(100)

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match=r"1.*99"):
            validate_price(-5)


class TestCentsToDisplay:
    def test_basic(self) -> None:
        assert cents_to_display(6500) == "$65.00"

    def test_zero(self) -> None:
        assert cents_to_display(0) == "$0.00"

    def test_one_cent(self) -> None:
        assert cents_to_display(1) == "$0.01"

    def test_large(self) -> None:
        assert cents_to_display(150000) == "$1,500.00"

    def test_exact_dollar(self) -> None:
        assert cents_to_display(10000) == "$100.00"


class TestCalculateFee:
    def test_basic(self) -> None:
        # 6500 * 20 / 10000 = 13.0 → 13
        assert calculate_fee(6500, 20) == 13

    def test_ceiling_rounds_up(self) -> None:
        # 6501 * 20 / 10000 = 13.002 → ceil = 14
        assert calculate_fee(6501, 20) == 14

    def test_zero_fee_rate(self) -> None:
        assert calculate_fee(6500, 0) == 0

    def test_zero_value(self) -> None:
        assert calculate_fee(0, 20) == 0

    def test_small_value(self) -> None:
        # 1 * 20 / 10000 = 0.002 → ceil = 1
        assert calculate_fee(1, 20) == 1

    def test_exact_division(self) -> None:
        # 10000 * 10 / 10000 = 10.0 → 10
        assert calculate_fee(10000, 10) == 10
