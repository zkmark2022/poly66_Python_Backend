"""Tests for AMM self-trade exemption and UUID case-insensitive comparison."""
import pytest
from src.pm_risk.rules.self_trade import AMM_USER_ID, is_self_trade

AMM_UPPER = "00000000-0000-4000-A000-000000000001"
AMM_LOWER = "00000000-0000-4000-a000-000000000001"
USER_A = "11111111-1111-4111-b111-111111111111"
USER_B = "22222222-2222-4222-b222-222222222222"


class TestSelfTradeBasic:
    def test_same_user_is_self_trade(self):
        assert is_self_trade(USER_A, USER_A) is True

    def test_different_users_not_self_trade(self):
        assert is_self_trade(USER_A, USER_B) is False


class TestAmmExemption:
    def test_amm_incoming_not_self_trade(self):
        """AMM as incoming order should never be flagged as self-trade."""
        assert is_self_trade(AMM_LOWER, USER_A) is False

    def test_amm_resting_not_self_trade(self):
        """AMM as resting order should never be flagged as self-trade."""
        assert is_self_trade(USER_A, AMM_LOWER) is False

    def test_amm_both_sides_not_self_trade(self):
        """AMM on both sides should not be flagged as self-trade."""
        assert is_self_trade(AMM_LOWER, AMM_LOWER) is False


class TestUuidCaseInsensitive:
    def test_amm_uppercase_incoming_exempt(self):
        """Uppercase AMM UUID as incoming should be exempt."""
        assert is_self_trade(AMM_UPPER, USER_A) is False

    def test_amm_uppercase_resting_exempt(self):
        """Uppercase AMM UUID as resting should be exempt."""
        assert is_self_trade(USER_A, AMM_UPPER) is False

    def test_amm_mixed_case_exempt(self):
        """Mixed-case AMM UUID should still be exempt."""
        mixed = "00000000-0000-4000-A000-000000000001"
        assert is_self_trade(mixed, USER_A) is False
        assert is_self_trade(USER_A, mixed) is False

    def test_same_user_uppercase_is_self_trade(self):
        """Regular users with same UUID in uppercase are still self-trade."""
        upper = USER_A.upper()
        lower = USER_A.lower()
        assert is_self_trade(upper, lower) is True

    def test_amm_constant_value(self):
        """AMM_USER_ID constant should match expected value (case-insensitive)."""
        assert AMM_USER_ID.lower() == "00000000-0000-4000-a000-000000000001"
