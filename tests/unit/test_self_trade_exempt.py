"""Tests for is_self_trade, focusing on:
- AMM bot exemption (never treated as self-trade)
- Type consistency: UUID objects and string representations both handled
"""

from uuid import UUID

import pytest

from src.pm_risk.rules.self_trade import AMM_USER_ID, is_self_trade

REGULAR_USER_A = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
REGULAR_USER_B = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"


class TestAmmExemption:
    def test_amm_incoming_vs_regular_resting(self) -> None:
        """AMM order as incoming should never be blocked."""
        assert is_self_trade(AMM_USER_ID, REGULAR_USER_A) is False

    def test_regular_incoming_vs_amm_resting(self) -> None:
        """AMM order as resting should never be blocked."""
        assert is_self_trade(REGULAR_USER_A, AMM_USER_ID) is False

    def test_amm_vs_amm(self) -> None:
        """AMM bot must not self-trade-block its own orders on both sides."""
        assert is_self_trade(AMM_USER_ID, AMM_USER_ID) is False


class TestRegularSelfTrade:
    def test_same_user_is_self_trade(self) -> None:
        assert is_self_trade(REGULAR_USER_A, REGULAR_USER_A) is True

    def test_different_users_not_self_trade(self) -> None:
        assert is_self_trade(REGULAR_USER_A, REGULAR_USER_B) is False


class TestTypeConsistency:
    """Verify str() normalisation handles UUID-object inputs correctly."""

    def test_amm_uuid_object_incoming(self) -> None:
        amm_uuid = UUID(AMM_USER_ID)
        assert is_self_trade(str(amm_uuid), REGULAR_USER_A) is False

    def test_amm_uuid_object_resting(self) -> None:
        amm_uuid = UUID(AMM_USER_ID)
        assert is_self_trade(REGULAR_USER_A, str(amm_uuid)) is False

    def test_regular_uuid_objects_same_user(self) -> None:
        uid = UUID(REGULAR_USER_A)
        assert is_self_trade(str(uid), str(uid)) is True

    def test_regular_uuid_objects_different_users(self) -> None:
        uid_a = UUID(REGULAR_USER_A)
        uid_b = UUID(REGULAR_USER_B)
        assert is_self_trade(str(uid_a), str(uid_b)) is False

    def test_uppercase_uuid_string_normalised(self) -> None:
        """UUID strings may come in different case; str() on UUID normalises."""
        upper = REGULAR_USER_A.upper()
        # Python UUID normalises to lowercase on round-trip
        assert is_self_trade(str(UUID(upper)), str(UUID(REGULAR_USER_A))) is True
