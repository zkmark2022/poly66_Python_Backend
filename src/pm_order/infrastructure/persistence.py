# src/pm_order/infrastructure/persistence.py
"""OrderRepository — raw SQL persistence implementation."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_order.domain.models import Order

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_INSERT_ORDER_SQL = text("""
    INSERT INTO orders (id, client_order_id, market_id, user_id,
        original_side, original_direction, original_price,
        book_type, book_direction, book_price, price_type, time_in_force,
        quantity, filled_quantity, remaining_quantity,
        frozen_amount, frozen_asset_type, status)
    VALUES (:id, :client_order_id, :market_id, :user_id,
        :original_side, :original_direction, :original_price,
        :book_type, :book_direction, :book_price, 'LIMIT', :time_in_force,
        :quantity, 0, :quantity, :frozen_amount, :frozen_asset_type, :status)
""")

_UPDATE_ORDER_SQL = text("""
    UPDATE orders
    SET status = :status, filled_quantity = :filled_quantity,
        remaining_quantity = :remaining_quantity,
        frozen_amount = :frozen_amount, updated_at = NOW()
    WHERE id = :id
""")

_SELECT_COLUMNS = """
    id, client_order_id, market_id, user_id,
    original_side, original_direction, original_price,
    book_type, book_direction, book_price, time_in_force,
    quantity, filled_quantity, remaining_quantity,
    frozen_amount, frozen_asset_type, status, cancel_reason, created_at, updated_at
"""

_GET_ORDER_BY_ID_SQL = text(f"""
    SELECT {_SELECT_COLUMNS}
    FROM orders WHERE id = :id
""")

_GET_ORDER_BY_CLIENT_ID_SQL = text(f"""
    SELECT {_SELECT_COLUMNS}
    FROM orders WHERE client_order_id = :client_order_id AND user_id = :user_id
""")

_LIST_ORDERS_SQL = text(f"""
    SELECT {_SELECT_COLUMNS}
    FROM orders
    WHERE user_id = :user_id
      AND (CAST(:market_id AS TEXT) IS NULL OR market_id = :market_id)
      AND (CAST(:cursor_id AS TEXT) IS NULL OR id < :cursor_id)
      AND (CAST(:statuses_csv AS TEXT) IS NULL
           OR status = ANY(string_to_array(CAST(:statuses_csv AS TEXT), ',')))
    ORDER BY id DESC
    LIMIT :limit
""")


# ---------------------------------------------------------------------------
# Row mapper
# ---------------------------------------------------------------------------


def _row_to_order(row: Any) -> Order:
    """Convert a DB result row to an Order domain object."""
    return Order(
        id=row.id,
        client_order_id=row.client_order_id,
        market_id=row.market_id,
        user_id=row.user_id,
        original_side=row.original_side,
        original_direction=row.original_direction,
        original_price=row.original_price,
        book_type=row.book_type,
        book_direction=row.book_direction,
        book_price=row.book_price,
        time_in_force=row.time_in_force,
        quantity=row.quantity,
        filled_quantity=row.filled_quantity,
        frozen_amount=row.frozen_amount,
        frozen_asset_type=row.frozen_asset_type,
        status=row.status,
        cancel_reason=row.cancel_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class OrderRepository:
    """Concrete implementation of OrderRepositoryProtocol using raw SQL."""

    async def save(self, order: Order, db: AsyncSession) -> None:
        await db.execute(
            _INSERT_ORDER_SQL,
            {
                "id": order.id,
                "client_order_id": order.client_order_id,
                "market_id": order.market_id,
                "user_id": order.user_id,
                "original_side": order.original_side,
                "original_direction": order.original_direction,
                "original_price": order.original_price,
                "book_type": order.book_type,
                "book_direction": order.book_direction,
                "book_price": order.book_price,
                "time_in_force": order.time_in_force,
                "quantity": order.quantity,
                "frozen_amount": order.frozen_amount,
                "frozen_asset_type": order.frozen_asset_type,
                "status": order.status,
            },
        )

    async def get_by_id(self, order_id: str, db: AsyncSession) -> Order | None:
        result = await db.execute(_GET_ORDER_BY_ID_SQL, {"id": order_id})
        row = result.fetchone()
        return _row_to_order(row) if row else None

    async def get_by_client_order_id(
        self, client_order_id: str, user_id: str, db: AsyncSession
    ) -> Order | None:
        result = await db.execute(
            _GET_ORDER_BY_CLIENT_ID_SQL,
            {"client_order_id": client_order_id, "user_id": user_id},
        )
        row = result.fetchone()
        return _row_to_order(row) if row else None

    async def update_status(self, order: Order, db: AsyncSession) -> None:
        await db.execute(
            _UPDATE_ORDER_SQL,
            {
                "id": order.id,
                "status": order.status,
                "filled_quantity": order.filled_quantity,
                "remaining_quantity": order.remaining_quantity,
                "frozen_amount": order.frozen_amount,
            },
        )

    async def list_by_user(
        self,
        user_id: str,
        market_id: str | None,
        statuses: list[str] | None,
        limit: int,
        cursor_id: str | None,
        db: AsyncSession,
    ) -> list[Order]:
        statuses_csv = ",".join(statuses) if statuses else None
        result = await db.execute(
            _LIST_ORDERS_SQL,
            {
                "user_id": user_id,
                "market_id": market_id,
                "cursor_id": cursor_id,
                "limit": limit,
                "statuses_csv": statuses_csv,
            },
        )
        rows = result.fetchall()
        return [_row_to_order(row) for row in rows]
