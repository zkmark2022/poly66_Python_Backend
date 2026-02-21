"""Unit tests for AccountApplicationService using a mock repository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pm_account.application.schemas import (
    BalanceResponse,
    DepositResponse,
    LedgerResponse,
    WithdrawResponse,
)
from src.pm_account.application.service import AccountApplicationService
from src.pm_account.domain.models import Account, LedgerEntry


def _make_account(available: int = 100000, frozen: int = 0) -> Account:
    return Account(
        id="uuid-1",
        user_id="user-1",
        available_balance=available,
        frozen_balance=frozen,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_ledger_entry(
    entry_id: int = 1,
    amount: int = 10000,
    balance_after: int = 110000,
    entry_type: str = "DEPOSIT",
) -> LedgerEntry:
    return LedgerEntry(
        id=entry_id,
        user_id="user-1",
        entry_type=entry_type,
        amount=amount,
        balance_after=balance_after,
        created_at=datetime.now(UTC),
    )


class TestGetBalance:
    async def test_returns_balance_response(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.get_account_by_user_id.return_value = _make_account(150000, 6500)
        svc = AccountApplicationService(repo=mock_repo)
        db = MagicMock()

        result = await svc.get_balance(db, "user-1")

        assert isinstance(result, BalanceResponse)
        assert result.available_balance_cents == 150000
        assert result.frozen_balance_cents == 6500
        assert result.total_balance_cents == 156500
        assert result.available_balance_display == "$1,500.00"

    async def test_zero_balance(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.get_account_by_user_id.return_value = _make_account(0, 0)
        svc = AccountApplicationService(repo=mock_repo)
        db = MagicMock()

        result = await svc.get_balance(db, "user-1")

        assert result.available_balance_cents == 0
        assert result.available_balance_display == "$0.00"
        assert result.total_balance_cents == 0


class TestDeposit:
    async def test_returns_deposit_response(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.deposit.return_value = (
            _make_account(110000),
            _make_ledger_entry(1, 10000, 110000),
        )
        svc = AccountApplicationService(repo=mock_repo)
        db = AsyncMock()

        result = await svc.deposit(db, "user-1", 10000)

        assert isinstance(result, DepositResponse)
        assert result.deposited_cents == 10000
        assert result.available_balance_cents == 110000
        assert result.ledger_entry_id == 1
        assert result.deposited_display == "$100.00"
        db.commit.assert_awaited_once()


class TestWithdraw:
    async def test_returns_withdraw_response(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.withdraw.return_value = (
            _make_account(90000),
            _make_ledger_entry(2, -10000, 90000, "WITHDRAW"),
        )
        svc = AccountApplicationService(repo=mock_repo)
        db = AsyncMock()

        result = await svc.withdraw(db, "user-1", 10000)

        assert isinstance(result, WithdrawResponse)
        assert result.withdrawn_cents == 10000
        assert result.available_balance_cents == 90000
        assert result.ledger_entry_id == 2
        db.commit.assert_awaited_once()


class TestListLedger:
    async def test_returns_empty_ledger(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.list_ledger_entries.return_value = []
        svc = AccountApplicationService(repo=mock_repo)
        db = MagicMock()

        result = await svc.list_ledger(db, "user-1", cursor=None, limit=20, entry_type=None)

        assert isinstance(result, LedgerResponse)
        assert result.items == []
        assert result.has_more is False
        assert result.next_cursor is None

    async def test_returns_items_no_more(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.list_ledger_entries.return_value = [
            _make_ledger_entry(5, 10000, 110000)
        ]
        svc = AccountApplicationService(repo=mock_repo)
        db = MagicMock()

        result = await svc.list_ledger(db, "user-1", cursor=None, limit=20, entry_type=None)

        assert len(result.items) == 1
        assert result.items[0].id == 5
        assert result.has_more is False
        assert result.next_cursor is None

    async def test_returns_next_cursor_when_full_page(self) -> None:
        mock_repo = AsyncMock()
        # Service fetches limit+1, so return 21 items to trigger has_more=True with limit=20
        entries = [_make_ledger_entry(i, 1000, 100000) for i in range(21, 0, -1)]
        mock_repo.list_ledger_entries.return_value = entries
        svc = AccountApplicationService(repo=mock_repo)
        db = MagicMock()

        result = await svc.list_ledger(db, "user-1", cursor=None, limit=20, entry_type=None)

        assert result.has_more is True
        assert result.next_cursor is not None
        assert len(result.items) == 20  # 21 fetched, but only first 20 returned
