"""Unit tests for self-trade exemption logic."""
from uuid import UUID

import pytest

from src.pm_account.domain.constants import AMM_USER_ID
from src.pm_risk.rules.self_trade import SELF_TRADE_EXEMPT_USERS, is_self_trade

REGULAR_USER_A = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
REGULAR_USER_B = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"


class TestSelfTradeExempt:
    def test_amm_vs_amm_not_blocked(self) -> None:
        assert is_self_trade(AMM_USER_ID, AMM_USER_ID) is False

    def test_amm_incoming_vs_user_resting_not_blocked(self) -> None:
        assert is_self_trade(AMM_USER_ID, "user-123") is False

    def test_user_incoming_vs_amm_resting_not_blocked(self) -> None:
        assert is_self_trade("user-123", AMM_USER_ID) is False

    def test_regular_user_self_trade_blocked(self) -> None:
        assert is_self_trade("user-123", "user-123") is True

    def test_different_regular_users_not_blocked(self) -> None:
        assert is_self_trade("user-aaa", "user-bbb") is False

    def test_exempt_set_contains_amm(self) -> None:
        assert AMM_USER_ID in SELF_TRADE_EXEMPT_USERS

    def test_amm_user_id_is_string(self) -> None:
        assert isinstance(AMM_USER_ID, str)
        assert AMM_USER_ID == "00000000-0000-4000-a000-000000000001"


class TestAmmExemption:
    def test_amm_incoming_vs_regular_resting(self) -> None:
        assert is_self_trade(AMM_USER_ID, REGULAR_USER_A) is False

    def test_regular_incoming_vs_amm_resting(self) -> None:
        assert is_self_trade(REGULAR_USER_A, AMM_USER_ID) is False

    def test_amm_vs_amm(self) -> None:
        assert is_self_trade(AMM_USER_ID, AMM_USER_ID) is False


class TestRegularSelfTrade:
    def test_same_user_is_self_trade(self) -> None:
        assert is_self_trade(REGULAR_USER_A, REGULAR_USER_A) is True

    def test_different_users_not_self_trade(self) -> None:
        assert is_self_trade(REGULAR_USER_A, REGULAR_USER_B) is False


class TestTypeConsistency:
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
        upper = REGULAR_USER_A.upper()
        assert is_self_trade(str(UUID(upper)), str(UUID(REGULAR_USER_A))) is True
