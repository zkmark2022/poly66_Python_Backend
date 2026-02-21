"""AccountApplicationService — thin composition layer.

Combines repository calls with schema transformations.
Deposit and withdraw use explicit commit/rollback for transaction management,
since the SQLAlchemy session may have autobegin active from upstream dependencies.
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
from src.pm_account.domain.models import Account, LedgerEntry, Position
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

    async def freeze_funds(
        self,
        db: AsyncSession,
        user_id: str,
        amount: int,
        ref_type: str,
        ref_id: str,
        description: str,
    ) -> tuple[Account, LedgerEntry]:
        """Freeze funds for an order. Caller must manage transaction."""
        return await self._repo.freeze_funds(db, user_id, amount, ref_type, ref_id, description)

    async def unfreeze_funds(
        self,
        db: AsyncSession,
        user_id: str,
        amount: int,
        ref_type: str,
        ref_id: str,
        description: str,
    ) -> tuple[Account, LedgerEntry]:
        """Unfreeze funds when order is cancelled. Caller must manage transaction."""
        return await self._repo.unfreeze_funds(db, user_id, amount, ref_type, ref_id, description)

    async def get_or_create_position(
        self, db: AsyncSession, user_id: str, market_id: str
    ) -> Position:
        """Get or create position row. Caller must manage transaction."""
        return await self._repo.get_or_create_position(db, user_id, market_id)

    async def freeze_yes_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position:
        """Freeze YES shares for a sell order. Caller must manage transaction."""
        return await self._repo.freeze_yes_position(db, user_id, market_id, quantity)

    async def unfreeze_yes_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position:
        """Unfreeze YES shares when order is cancelled. Caller must manage transaction."""
        return await self._repo.unfreeze_yes_position(db, user_id, market_id, quantity)

    async def freeze_no_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position:
        """Freeze NO shares for a sell order. Caller must manage transaction."""
        return await self._repo.freeze_no_position(db, user_id, market_id, quantity)

    async def unfreeze_no_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position:
        """Unfreeze NO shares when order is cancelled. Caller must manage transaction."""
        return await self._repo.unfreeze_no_position(db, user_id, market_id, quantity)
