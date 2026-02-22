# src/pm_account/infrastructure/positions_repository.py
"""Read-only positions queries."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_LIST_SQL = text("""
    SELECT market_id, yes_volume, yes_cost_sum, no_volume, no_cost_sum
    FROM positions
    WHERE user_id = :user_id
      AND (yes_volume > 0 OR no_volume > 0)
    ORDER BY market_id
""")

_GET_SQL = text("""
    SELECT market_id, yes_volume, yes_cost_sum, no_volume, no_cost_sum
    FROM positions
    WHERE user_id = :user_id AND market_id = :market_id
""")


class PositionsRepository:
    async def list_by_user(
        self, user_id: str, db: AsyncSession
    ) -> list[dict[str, Any]]:
        rows = (await db.execute(_LIST_SQL, {"user_id": user_id})).fetchall()
        return [_row_to_dict(r) for r in rows]

    async def get_by_market(
        self, user_id: str, market_id: str, db: AsyncSession
    ) -> dict[str, Any] | None:
        row = (
            await db.execute(_GET_SQL, {"user_id": user_id, "market_id": market_id})
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "market_id": row.market_id,
        "yes_volume": row.yes_volume,
        "yes_cost_sum": row.yes_cost_sum,
        "no_volume": row.no_volume,
        "no_cost_sum": row.no_cost_sum,
    }
