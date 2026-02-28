"""Unit tests for self-trade exemption logic."""
import pytest

from src.pm_account.domain.constants import AMM_USER_ID
from src.pm_risk.rules.self_trade import SELF_TRADE_EXEMPT_USERS, is_self_trade


class TestSelfTradeExempt:
    def test_amm_vs_amm_not_blocked(self) -> None:
        """AMM trading against its own resting order must NOT be blocked."""
        assert is_self_trade(AMM_USER_ID, AMM_USER_ID) is False

    def test_amm_incoming_vs_user_resting_not_blocked(self) -> None:
        """AMM incoming vs regular user resting — not a self-trade."""
        assert is_self_trade(AMM_USER_ID, "user-123") is False

    def test_user_incoming_vs_amm_resting_not_blocked(self) -> None:
        """Regular user incoming vs AMM resting — not a self-trade."""
        assert is_self_trade("user-123", AMM_USER_ID) is False

    def test_regular_user_self_trade_blocked(self) -> None:
        """Normal user trading against themselves must still be blocked."""
        assert is_self_trade("user-123", "user-123") is True

    def test_different_regular_users_not_blocked(self) -> None:
        assert is_self_trade("user-aaa", "user-bbb") is False

    def test_exempt_set_contains_amm(self) -> None:
        assert AMM_USER_ID in SELF_TRADE_EXEMPT_USERS

    def test_amm_user_id_is_string(self) -> None:
        """Ensure the constant is a str, not a UUID object."""
        assert isinstance(AMM_USER_ID, str)
        assert AMM_USER_ID == "00000000-0000-4000-a000-000000000001"
