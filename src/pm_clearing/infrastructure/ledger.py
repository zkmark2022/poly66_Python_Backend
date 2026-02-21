"""DB helpers for ledger_entries and wal_events.

Called from MatchingEngine within a transaction.
"""
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.datetime_utils import utc_now
from src.pm_common.id_generator import generate_id

_INSERT_LEDGER_SQL = text("""
    INSERT INTO ledger_entries
        (user_id, entry_type, amount, balance_after, reference_type, reference_id)
    VALUES (:user_id, :entry_type, :amount, :balance_after, :reference_type, :reference_id)
""")

_INSERT_WAL_SQL = text("""
    INSERT INTO wal_events (id, event_type, order_id, market_id, user_id, payload, created_at)
    VALUES (:id, :event_type, :order_id, :market_id, :user_id, :payload, :created_at)
""")


async def write_ledger(
    user_id: str,
    entry_type: str,
    amount: int,
    balance_after: int,
    reference_type: str,
    reference_id: str,
    db: AsyncSession,
) -> None:
    """Insert one row into ledger_entries within the caller's transaction."""
    await db.execute(
        _INSERT_LEDGER_SQL,
        {
            "user_id": user_id,
            "entry_type": entry_type,
            "amount": amount,
            "balance_after": balance_after,
            "reference_type": reference_type,
            "reference_id": reference_id,
        },
    )


async def write_wal_event(
    event_type: str,
    order_id: str,
    market_id: str,
    user_id: str,
    payload: dict[str, object],
    db: AsyncSession,
) -> None:
    """Insert one row into wal_events within the caller's transaction."""
    await db.execute(
        _INSERT_WAL_SQL,
        {
            "id": generate_id(),
            "event_type": event_type,
            "order_id": order_id,
            "market_id": market_id,
            "user_id": user_id,
            "payload": json.dumps(payload),
            "created_at": utc_now(),
        },
    )
