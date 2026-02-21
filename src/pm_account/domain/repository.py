"""Repository Protocol — dependency inversion for testability.

Unit tests inject a mock that conforms to this Protocol.
Infrastructure layer provides the real implementation.
"""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_account.domain.models import Account, LedgerEntry, Position


class AccountRepositoryProtocol(Protocol):
    async def get_account_by_user_id(
        self, db: AsyncSession, user_id: str
    ) -> Account | None: ...

    async def deposit(
        self, db: AsyncSession, user_id: str, amount: int
    ) -> tuple[Account, LedgerEntry]: ...

    async def withdraw(
        self, db: AsyncSession, user_id: str, amount: int
    ) -> tuple[Account, LedgerEntry]: ...

    async def freeze_funds(
        self,
        db: AsyncSession,
        user_id: str,
        amount: int,
        ref_type: str,
        ref_id: str,
        description: str,
    ) -> tuple[Account, LedgerEntry]: ...

    async def unfreeze_funds(
        self,
        db: AsyncSession,
        user_id: str,
        amount: int,
        ref_type: str,
        ref_id: str,
        description: str,
    ) -> tuple[Account, LedgerEntry]: ...

    async def get_or_create_position(
        self, db: AsyncSession, user_id: str, market_id: str
    ) -> Position: ...

    async def freeze_yes_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position: ...

    async def unfreeze_yes_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position: ...

    async def freeze_no_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position: ...

    async def unfreeze_no_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position: ...

    async def list_ledger_entries(
        self,
        db: AsyncSession,
        user_id: str,
        cursor_id: int | None,
        limit: int,
        entry_type: str | None,
    ) -> list[LedgerEntry]: ...
