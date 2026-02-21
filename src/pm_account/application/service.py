"""AccountApplicationService — thin composition layer.

Combines repository calls with schema transformations.
Deposit and withdraw use `async with db.begin()` to manage transactions.
Other operations (get_balance, list_ledger) are read-only and run without explicit transaction.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_account.application.schemas import (
    BalanceResponse,
    DepositResponse,
    LedgerEntryItem,
    LedgerResponse,
    WithdrawResponse,
    cursor_decode,
    cursor_encode,
)
from src.pm_account.domain.repository import AccountRepositoryProtocol
from src.pm_account.infrastructure.persistence import AccountRepository
from src.pm_common.cents import cents_to_display
from src.pm_common.errors import InternalError


class AccountApplicationService:
    def __init__(self, repo: AccountRepositoryProtocol | None = None) -> None:
        self._repo: AccountRepositoryProtocol = repo or AccountRepository()

    async def get_balance(self, db: AsyncSession, user_id: str) -> BalanceResponse:
        account = await self._repo.get_account_by_user_id(db, user_id)
        if account is None:
            raise InternalError(f"Account not found for user {user_id}")
        return BalanceResponse.from_cents(
            user_id=user_id,
            available=account.available_balance,
            frozen=account.frozen_balance,
        )

    async def deposit(
        self, db: AsyncSession, user_id: str, amount_cents: int
    ) -> DepositResponse:
        try:
            account, entry = await self._repo.deposit(db, user_id, amount_cents)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return DepositResponse.from_result(
            available=account.available_balance,
            amount=amount_cents,
            entry_id=entry.id,
        )

    async def withdraw(
        self, db: AsyncSession, user_id: str, amount_cents: int
    ) -> WithdrawResponse:
        try:
            account, entry = await self._repo.withdraw(db, user_id, amount_cents)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return WithdrawResponse.from_result(
            available=account.available_balance,
            amount=amount_cents,
            entry_id=entry.id,
        )

    async def list_ledger(
        self,
        db: AsyncSession,
        user_id: str,
        cursor: str | None,
        limit: int,
        entry_type: str | None,
    ) -> LedgerResponse:
        cursor_id = cursor_decode(cursor)
        # Fetch limit+1 to detect has_more without a COUNT(*) query
        entries = await self._repo.list_ledger_entries(
            db, user_id, cursor_id, limit + 1, entry_type
        )
        has_more = len(entries) > limit
        page = entries[:limit]

        items = [
            LedgerEntryItem(
                id=e.id,
                entry_type=e.entry_type,
                amount_cents=e.amount,
                amount_display=cents_to_display(e.amount),
                balance_after_cents=e.balance_after,
                balance_after_display=cents_to_display(e.balance_after),
                reference_type=e.reference_type,
                reference_id=e.reference_id,
                description=e.description,
                created_at=e.created_at.isoformat() if e.created_at else "",
            )
            for e in page
        ]

        next_cursor = cursor_encode(page[-1].id) if has_more and page else None
        return LedgerResponse(items=items, next_cursor=next_cursor, has_more=has_more)
