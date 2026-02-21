# tests/unit/test_order_persistence.py
"""Unit tests for OrderRepository using MagicMock AsyncSession."""
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pm_order.domain.models import Order
from src.pm_order.infrastructure.persistence import OrderRepository


def _make_row(**kwargs: Any) -> MagicMock:
    """Create a mock row with all Order fields."""
    row = MagicMock()
    row.id = kwargs.get("id", "order-1")
    row.client_order_id = kwargs.get("client_order_id", "client-1")
    row.market_id = kwargs.get("market_id", "mkt-1")
    row.user_id = kwargs.get("user_id", "user-1")
    row.original_side = kwargs.get("original_side", "YES")
    row.original_direction = kwargs.get("original_direction", "BUY")
    row.original_price = kwargs.get("original_price", 65)
    row.book_type = kwargs.get("book_type", "NATIVE_BUY")
    row.book_direction = kwargs.get("book_direction", "BUY")
    row.book_price = kwargs.get("book_price", 65)
    row.time_in_force = kwargs.get("time_in_force", "GTC")
    row.quantity = kwargs.get("quantity", 100)
    row.filled_quantity = kwargs.get("filled_quantity", 0)
    row.remaining_quantity = kwargs.get("remaining_quantity", 100)
    row.frozen_amount = kwargs.get("frozen_amount", 6700)
    row.frozen_asset_type = kwargs.get("frozen_asset_type", "FUNDS")
    row.status = kwargs.get("status", "OPEN")
    row.cancel_reason = kwargs.get("cancel_reason")
    row.created_at = kwargs.get("created_at", datetime.now(UTC))
    row.updated_at = kwargs.get("updated_at", datetime.now(UTC))
    return row


def _make_order(**kwargs: Any) -> Order:
    return Order(
        id=kwargs.get("id", "order-1"),
        client_order_id=kwargs.get("client_order_id", "client-1"),
        market_id=kwargs.get("market_id", "mkt-1"),
        user_id=kwargs.get("user_id", "user-1"),
        original_side=kwargs.get("original_side", "YES"),
        original_direction=kwargs.get("original_direction", "BUY"),
        original_price=kwargs.get("original_price", 65),
        book_type=kwargs.get("book_type", "NATIVE_BUY"),
        book_direction=kwargs.get("book_direction", "BUY"),
        book_price=kwargs.get("book_price", 65),
        quantity=kwargs.get("quantity", 100),
        frozen_amount=kwargs.get("frozen_amount", 6700),
        frozen_asset_type=kwargs.get("frozen_asset_type", "FUNDS"),
        time_in_force=kwargs.get("time_in_force", "GTC"),
        status=kwargs.get("status", "OPEN"),
    )


class TestOrderRepository:
    @pytest.mark.asyncio
    async def test_save_executes_insert(self) -> None:
        db = AsyncMock()
        repo = OrderRepository()
        order = _make_order()
        await repo.save(order, db)
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_id_returns_order(self) -> None:
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = _make_row()
        db.execute.return_value = result_mock
        repo = OrderRepository()
        order = await repo.get_by_id("order-1", db)
        assert order is not None
        assert order.id == "order-1"
        assert order.status == "OPEN"

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_when_not_found(self) -> None:
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None
        db.execute.return_value = result_mock
        repo = OrderRepository()
        order = await repo.get_by_id("missing", db)
        assert order is None

    @pytest.mark.asyncio
    async def test_get_by_client_order_id_returns_order(self) -> None:
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = _make_row(client_order_id="client-abc")
        db.execute.return_value = result_mock
        repo = OrderRepository()
        order = await repo.get_by_client_order_id("client-abc", "user-1", db)
        assert order is not None
        assert order.client_order_id == "client-abc"

    @pytest.mark.asyncio
    async def test_update_status_executes(self) -> None:
        db = AsyncMock()
        repo = OrderRepository()
        order = _make_order(status="FILLED", filled_quantity=100, remaining_quantity=0)
        await repo.update_status(order, db)
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_by_user_returns_empty(self) -> None:
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute.return_value = result_mock
        repo = OrderRepository()
        orders = await repo.list_by_user("user-1", None, None, None, None, 20, None, db)
        assert orders == []

    @pytest.mark.asyncio
    async def test_list_by_user_returns_orders(self) -> None:
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [_make_row(), _make_row(id="order-2")]
        db.execute.return_value = result_mock
        repo = OrderRepository()
        orders = await repo.list_by_user("user-1", None, None, None, None, 20, None, db)
        assert len(orders) == 2

    @pytest.mark.asyncio
    async def test_row_to_order_maps_cancel_reason(self) -> None:
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = _make_row(
            id="order-cancel",
            status="CANCELLED",
            cancel_reason="USER_REQUESTED",
        )
        db.execute.return_value = result_mock
        repo = OrderRepository()
        order = await repo.get_by_id("order-cancel", db)
        assert order is not None
        assert order.status == "CANCELLED"
        assert order.cancel_reason == "USER_REQUESTED"

    @pytest.mark.asyncio
    async def test_row_to_order_computes_remaining_quantity(self) -> None:
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = _make_row(
            quantity=100,
            filled_quantity=40,
            remaining_quantity=60,
        )
        db.execute.return_value = result_mock
        repo = OrderRepository()
        order = await repo.get_by_id("order-1", db)
        assert order is not None
        # remaining_quantity is computed in __post_init__ as quantity - filled_quantity
        assert order.remaining_quantity == 60

    @pytest.mark.asyncio
    async def test_list_by_user_with_market_id_filter(self) -> None:
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [_make_row(market_id="mkt-specific")]
        db.execute.return_value = result_mock
        repo = OrderRepository()
        orders = await repo.list_by_user("user-1", "mkt-specific", None, None, None, 10, None, db)
        assert len(orders) == 1
        assert orders[0].market_id == "mkt-specific"

    @pytest.mark.asyncio
    async def test_list_by_user_with_cursor(self) -> None:
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [_make_row(id="order-5")]
        db.execute.return_value = result_mock
        repo = OrderRepository()
        orders = await repo.list_by_user("user-1", None, None, None, None, 20, "order-10", db)
        assert len(orders) == 1
        assert orders[0].id == "order-5"
