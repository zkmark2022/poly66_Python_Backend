from datetime import UTC, datetime

from src.pm_account.domain.enums import LedgerEntryType
from src.pm_account.domain.models import Account, LedgerEntry, Position


class TestAccount:
    def test_total_balance(self) -> None:
        account = Account(
            id="uuid-123",
            user_id="user-1",
            available_balance=100000,
            frozen_balance=6500,
            version=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert account.total_balance == 106500

    def test_total_balance_all_frozen(self) -> None:
        account = Account(
            id="uuid-123",
            user_id="user-1",
            available_balance=0,
            frozen_balance=50000,
            version=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert account.total_balance == 50000


class TestPosition:
    def test_defaults(self) -> None:
        pos = Position(user_id="user-1", market_id="market-1")
        assert pos.yes_volume == 0
        assert pos.yes_cost_sum == 0
        assert pos.yes_pending_sell == 0
        assert pos.no_volume == 0
        assert pos.no_cost_sum == 0
        assert pos.no_pending_sell == 0

    def test_available_yes(self) -> None:
        pos = Position(
            user_id="user-1",
            market_id="market-1",
            yes_volume=100,
            yes_pending_sell=30,
        )
        assert pos.available_yes == 70

    def test_available_no(self) -> None:
        pos = Position(
            user_id="user-1",
            market_id="market-1",
            no_volume=50,
            no_pending_sell=20,
        )
        assert pos.available_no == 30


class TestLedgerEntry:
    def test_optional_fields_default_to_none(self) -> None:
        from src.pm_common.enums import LedgerEntryType
        entry = LedgerEntry(
            id=1,
            user_id="user-1",
            entry_type=LedgerEntryType.DEPOSIT,
            amount=10000,
            balance_after=110000,
        )
        assert entry.reference_type is None
        assert entry.reference_id is None
        assert entry.description is None
        assert entry.created_at is None


class TestLedgerEntryType:
    def test_deposit_value(self) -> None:
        assert LedgerEntryType.DEPOSIT == "DEPOSIT"

    def test_all_16_types_exist(self) -> None:
        expected = {
            "DEPOSIT", "WITHDRAW",
            "ORDER_FREEZE", "ORDER_UNFREEZE",
            "MINT_COST", "MINT_RESERVE_IN",
            "BURN_REVENUE", "BURN_RESERVE_OUT",
            "TRANSFER_PAYMENT", "TRANSFER_RECEIPT",
            "NETTING", "NETTING_RESERVE_OUT",
            "FEE", "FEE_REVENUE",
            "SETTLEMENT_PAYOUT", "SETTLEMENT_VOID",
        }
        actual = {e.value for e in LedgerEntryType}
        assert actual == expected
