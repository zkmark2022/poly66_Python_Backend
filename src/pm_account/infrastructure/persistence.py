"""AccountRepository — concrete implementation of AccountRepositoryProtocol.

All balance-mutating operations use atomic PostgreSQL UPDATE ... RETURNING.
A result of 0 rows means a business constraint was violated (insufficient funds/shares).

Transaction ownership: The CALLER (application service or router) is responsible for
starting and committing the transaction via `async with db.begin()`.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_account.domain.models import Account, LedgerEntry, Position
from src.pm_common.enums import LedgerEntryType
from src.pm_common.errors import InsufficientBalanceError, InsufficientPositionError, InternalError

# ---------------------------------------------------------------------------
# SQL: accounts mutations
# ---------------------------------------------------------------------------

_DEPOSIT_SQL = text("""
    UPDATE accounts
    SET available_balance = available_balance + :amount,
        version = version + 1,
        updated_at = NOW()
    WHERE user_id = :user_id
    RETURNING id, user_id, available_balance, frozen_balance, version, created_at, updated_at
""")

_WITHDRAW_SQL = text("""
    UPDATE accounts
    SET available_balance = available_balance - :amount,
        version = version + 1,
        updated_at = NOW()
    WHERE user_id = :user_id AND available_balance >= :amount
    RETURNING id, user_id, available_balance, frozen_balance, version, created_at, updated_at
""")

_FREEZE_FUNDS_SQL = text("""
    UPDATE accounts
    SET available_balance = available_balance - :amount,
        frozen_balance     = frozen_balance   + :amount,
        version = version + 1,
        updated_at = NOW()
    WHERE user_id = :user_id AND available_balance >= :amount
    RETURNING id, user_id, available_balance, frozen_balance, version, created_at, updated_at
""")

_UNFREEZE_FUNDS_SQL = text("""
    UPDATE accounts
    SET available_balance = available_balance + :amount,
        frozen_balance     = frozen_balance   - :amount,
        version = version + 1,
        updated_at = NOW()
    WHERE user_id = :user_id AND frozen_balance >= :amount
    RETURNING id, user_id, available_balance, frozen_balance, version, created_at, updated_at
""")

_INSERT_LEDGER_SQL = text("""
    INSERT INTO ledger_entries
        (user_id, entry_type, amount, balance_after,
         reference_type, reference_id, description)
    VALUES
        (:user_id, :entry_type, :amount, :balance_after,
         :reference_type, :reference_id, :description)
    RETURNING id, user_id, entry_type, amount, balance_after,
              reference_type, reference_id, description, created_at
""")

# ---------------------------------------------------------------------------
# SQL: positions mutations
# ---------------------------------------------------------------------------

_GET_OR_CREATE_POSITION_SQL = text("""
    INSERT INTO positions (user_id, market_id)
    VALUES (:user_id, :market_id)
    ON CONFLICT (user_id, market_id) DO UPDATE
        SET updated_at = NOW()
    RETURNING id, user_id, market_id,
              yes_volume, yes_cost_sum, yes_pending_sell,
              no_volume, no_cost_sum, no_pending_sell,
              created_at, updated_at
""")

_FREEZE_YES_SQL = text("""
    UPDATE positions
    SET yes_pending_sell = yes_pending_sell + :quantity,
        updated_at = NOW()
    WHERE user_id = :user_id
      AND market_id = :market_id
      AND (yes_volume - yes_pending_sell) >= :quantity
    RETURNING id, user_id, market_id,
              yes_volume, yes_cost_sum, yes_pending_sell,
              no_volume, no_cost_sum, no_pending_sell,
              created_at, updated_at
""")

_UNFREEZE_YES_SQL = text("""
    UPDATE positions
    SET yes_pending_sell = yes_pending_sell - :quantity,
        updated_at = NOW()
    WHERE user_id = :user_id
      AND market_id = :market_id
      AND yes_pending_sell >= :quantity
    RETURNING id, user_id, market_id,
              yes_volume, yes_cost_sum, yes_pending_sell,
              no_volume, no_cost_sum, no_pending_sell,
              created_at, updated_at
""")

_FREEZE_NO_SQL = text("""
    UPDATE positions
    SET no_pending_sell = no_pending_sell + :quantity,
        updated_at = NOW()
    WHERE user_id = :user_id
      AND market_id = :market_id
      AND (no_volume - no_pending_sell) >= :quantity
    RETURNING id, user_id, market_id,
              yes_volume, yes_cost_sum, yes_pending_sell,
              no_volume, no_cost_sum, no_pending_sell,
              created_at, updated_at
""")

_UNFREEZE_NO_SQL = text("""
    UPDATE positions
    SET no_pending_sell = no_pending_sell - :quantity,
        updated_at = NOW()
    WHERE user_id = :user_id
      AND market_id = :market_id
      AND no_pending_sell >= :quantity
    RETURNING id, user_id, market_id,
              yes_volume, yes_cost_sum, yes_pending_sell,
              no_volume, no_cost_sum, no_pending_sell,
              created_at, updated_at
""")

_LIST_LEDGER_SQL = text("""
    SELECT id, user_id, entry_type, amount, balance_after,
           reference_type, reference_id, description, created_at
    FROM ledger_entries
    WHERE user_id = :user_id
      AND (:cursor_id IS NULL OR id < :cursor_id)
      AND (:entry_type IS NULL OR entry_type = :entry_type)
    ORDER BY id DESC
    LIMIT :limit
""")

_GET_ACCOUNT_SQL = text("""
    SELECT id, user_id, available_balance, frozen_balance, version, created_at, updated_at
    FROM accounts
    WHERE user_id = :user_id
""")


def _row_to_account(row: object) -> Account:
    return Account(
        id=str(row.id),  # type: ignore[attr-defined]
        user_id=row.user_id,  # type: ignore[attr-defined]
        available_balance=row.available_balance,  # type: ignore[attr-defined]
        frozen_balance=row.frozen_balance,  # type: ignore[attr-defined]
        version=row.version,  # type: ignore[attr-defined]
        created_at=row.created_at,  # type: ignore[attr-defined]
        updated_at=row.updated_at,  # type: ignore[attr-defined]
    )


def _row_to_ledger(row: object) -> LedgerEntry:
    return LedgerEntry(
        id=row.id,  # type: ignore[attr-defined]
        user_id=row.user_id,  # type: ignore[attr-defined]
        entry_type=row.entry_type,  # type: ignore[attr-defined]
        amount=row.amount,  # type: ignore[attr-defined]
        balance_after=row.balance_after,  # type: ignore[attr-defined]
        reference_type=row.reference_type,  # type: ignore[attr-defined]
        reference_id=row.reference_id,  # type: ignore[attr-defined]
        description=row.description,  # type: ignore[attr-defined]
        created_at=row.created_at,  # type: ignore[attr-defined]
    )


def _row_to_position(row: object) -> Position:
    return Position(
        user_id=row.user_id,  # type: ignore[attr-defined]
        market_id=row.market_id,  # type: ignore[attr-defined]
        yes_volume=row.yes_volume,  # type: ignore[attr-defined]
        yes_cost_sum=row.yes_cost_sum,  # type: ignore[attr-defined]
        yes_pending_sell=row.yes_pending_sell,  # type: ignore[attr-defined]
        no_volume=row.no_volume,  # type: ignore[attr-defined]
        no_cost_sum=row.no_cost_sum,  # type: ignore[attr-defined]
        no_pending_sell=row.no_pending_sell,  # type: ignore[attr-defined]
        created_at=row.created_at,  # type: ignore[attr-defined]
        updated_at=row.updated_at,  # type: ignore[attr-defined]
    )


class AccountRepository:
    """Concrete repository — all operations atomic at the SQL level."""

    async def get_account_by_user_id(
        self, db: AsyncSession, user_id: str
    ) -> Account | None:
        result = await db.execute(_GET_ACCOUNT_SQL, {"user_id": user_id})
        row = result.fetchone()
        return _row_to_account(row) if row else None

    async def deposit(
        self, db: AsyncSession, user_id: str, amount: int
    ) -> tuple[Account, LedgerEntry]:
        result = await db.execute(_DEPOSIT_SQL, {"user_id": user_id, "amount": amount})
        row = result.fetchone()
        if row is None:
            raise InternalError(f"Account not found for user {user_id}")
        account = _row_to_account(row)
        ledger_result = await db.execute(
            _INSERT_LEDGER_SQL,
            {
                "user_id": user_id,
                "entry_type": LedgerEntryType.DEPOSIT,
                "amount": amount,
                "balance_after": account.available_balance,
                "reference_type": "DEPOSIT",
                "reference_id": None,
                "description": "Simulated deposit",
            },
        )
        ledger_row = ledger_result.fetchone()
        if ledger_row is None:
            raise InternalError("Ledger insert returned no rows — this should never happen")
        return account, _row_to_ledger(ledger_row)

    async def withdraw(
        self, db: AsyncSession, user_id: str, amount: int
    ) -> tuple[Account, LedgerEntry]:
        result = await db.execute(_WITHDRAW_SQL, {"user_id": user_id, "amount": amount})
        row = result.fetchone()
        if row is None:
            acc_result = await db.execute(_GET_ACCOUNT_SQL, {"user_id": user_id})
            acc_row = acc_result.fetchone()
            available = acc_row.available_balance if acc_row else 0
            raise InsufficientBalanceError(amount, available)
        account = _row_to_account(row)
        ledger_result = await db.execute(
            _INSERT_LEDGER_SQL,
            {
                "user_id": user_id,
                "entry_type": LedgerEntryType.WITHDRAW,
                "amount": -amount,
                "balance_after": account.available_balance,
                "reference_type": "WITHDRAW",
                "reference_id": None,
                "description": "Simulated withdrawal",
            },
        )
        ledger_row = ledger_result.fetchone()
        if ledger_row is None:
            raise InternalError("Ledger insert returned no rows — this should never happen")
        return account, _row_to_ledger(ledger_row)

    async def freeze_funds(
        self,
        db: AsyncSession,
        user_id: str,
        amount: int,
        ref_type: str,
        ref_id: str,
        description: str,
    ) -> tuple[Account, LedgerEntry]:
        result = await db.execute(_FREEZE_FUNDS_SQL, {"user_id": user_id, "amount": amount})
        row = result.fetchone()
        if row is None:
            acc_result = await db.execute(_GET_ACCOUNT_SQL, {"user_id": user_id})
            acc_row = acc_result.fetchone()
            available = acc_row.available_balance if acc_row else 0
            raise InsufficientBalanceError(amount, available)
        account = _row_to_account(row)
        ledger_result = await db.execute(
            _INSERT_LEDGER_SQL,
            {
                "user_id": user_id,
                "entry_type": LedgerEntryType.ORDER_FREEZE,
                "amount": -amount,
                "balance_after": account.available_balance,
                "reference_type": ref_type,
                "reference_id": ref_id,
                "description": description,
            },
        )
        ledger_row = ledger_result.fetchone()
        if ledger_row is None:
            raise InternalError("Ledger insert returned no rows — this should never happen")
        return account, _row_to_ledger(ledger_row)

    async def unfreeze_funds(
        self,
        db: AsyncSession,
        user_id: str,
        amount: int,
        ref_type: str,
        ref_id: str,
        description: str,
    ) -> tuple[Account, LedgerEntry]:
        result = await db.execute(_UNFREEZE_FUNDS_SQL, {"user_id": user_id, "amount": amount})
        row = result.fetchone()
        if row is None:
            acc_result = await db.execute(_GET_ACCOUNT_SQL, {"user_id": user_id})
            acc_row = acc_result.fetchone()
            frozen = acc_row.frozen_balance if acc_row else 0
            raise InsufficientBalanceError(amount, frozen)
        account = _row_to_account(row)
        ledger_result = await db.execute(
            _INSERT_LEDGER_SQL,
            {
                "user_id": user_id,
                "entry_type": LedgerEntryType.ORDER_UNFREEZE,
                "amount": amount,
                "balance_after": account.available_balance,
                "reference_type": ref_type,
                "reference_id": ref_id,
                "description": description,
            },
        )
        ledger_row = ledger_result.fetchone()
        if ledger_row is None:
            raise InternalError("Ledger insert returned no rows — this should never happen")
        return account, _row_to_ledger(ledger_row)

    async def get_or_create_position(
        self, db: AsyncSession, user_id: str, market_id: str
    ) -> Position:
        result = await db.execute(
            _GET_OR_CREATE_POSITION_SQL, {"user_id": user_id, "market_id": market_id}
        )
        row = result.fetchone()
        if row is None:
            raise InternalError("Ledger insert returned no rows — this should never happen")
        return _row_to_position(row)

    async def freeze_yes_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position:
        result = await db.execute(
            _FREEZE_YES_SQL,
            {"user_id": user_id, "market_id": market_id, "quantity": quantity},
        )
        row = result.fetchone()
        if row is None:
            raise InsufficientPositionError(
                f"Insufficient YES shares to freeze: need {quantity}"
            )
        return _row_to_position(row)

    async def unfreeze_yes_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position:
        result = await db.execute(
            _UNFREEZE_YES_SQL,
            {"user_id": user_id, "market_id": market_id, "quantity": quantity},
        )
        row = result.fetchone()
        if row is None:
            raise InsufficientPositionError(
                f"Insufficient frozen YES shares to unfreeze: need {quantity}"
            )
        return _row_to_position(row)

    async def freeze_no_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position:
        result = await db.execute(
            _FREEZE_NO_SQL,
            {"user_id": user_id, "market_id": market_id, "quantity": quantity},
        )
        row = result.fetchone()
        if row is None:
            raise InsufficientPositionError(
                f"Insufficient NO shares to freeze: need {quantity}"
            )
        return _row_to_position(row)

    async def unfreeze_no_position(
        self, db: AsyncSession, user_id: str, market_id: str, quantity: int
    ) -> Position:
        result = await db.execute(
            _UNFREEZE_NO_SQL,
            {"user_id": user_id, "market_id": market_id, "quantity": quantity},
        )
        row = result.fetchone()
        if row is None:
            raise InsufficientPositionError(
                f"Insufficient frozen NO shares to unfreeze: need {quantity}"
            )
        return _row_to_position(row)

    async def list_ledger_entries(
        self,
        db: AsyncSession,
        user_id: str,
        cursor_id: int | None,
        limit: int,
        entry_type: str | None,
    ) -> list[LedgerEntry]:
        result = await db.execute(
            _LIST_LEDGER_SQL,
            {
                "user_id": user_id,
                "cursor_id": cursor_id,
                "entry_type": entry_type,
                "limit": limit,
            },
        )
        rows = result.fetchall()
        return [_row_to_ledger(row) for row in rows]
