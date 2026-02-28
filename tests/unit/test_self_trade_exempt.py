"""Test self-trade exemption for AMM. See data dictionary v1.3 §3.4 方案 A."""
from src.pm_risk.rules.self_trade import is_self_trade
from src.pm_account.domain.constants import AMM_USER_ID


class TestSelfTradeExemption:
    def test_amm_incoming_not_self_trade(self) -> None:
        """AMM as incoming order should NOT trigger self-trade."""
        assert is_self_trade(AMM_USER_ID, AMM_USER_ID) is False

    def test_amm_vs_normal_not_self_trade(self) -> None:
        assert is_self_trade(AMM_USER_ID, "user-123") is False

    def test_normal_vs_amm_not_self_trade(self) -> None:
        """Normal user incoming vs AMM resting — not self-trade (different users)."""
        assert is_self_trade("user-123", AMM_USER_ID) is False

    def test_normal_same_user_is_self_trade(self) -> None:
        """Normal user vs same user — still self-trade."""
        assert is_self_trade("user-123", "user-123") is True

    def test_normal_different_users_not_self_trade(self) -> None:
        assert is_self_trade("user-123", "user-456") is False
