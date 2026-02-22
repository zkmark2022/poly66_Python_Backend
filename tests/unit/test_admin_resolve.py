# tests/unit/test_admin_resolve.py
"""Unit tests for AdminService.resolve_market."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_resolve_active_market_calls_settle() -> None:
    from src.pm_admin.application.service import AdminService
    db = AsyncMock()
    # market row
    market_mock = MagicMock()
    market_mock.fetchone.return_value = MagicMock(status="ACTIVE", id="mkt-1")
    # open orders (empty)
    orders_mock = MagicMock()
    orders_mock.fetchall.return_value = []
    db.execute.side_effect = [market_mock, orders_mock]
    with patch("src.pm_admin.application.service.settle_market") as mock_settle:
        svc = AdminService()
        result = await svc.resolve_market("mkt-1", "YES", db)
    mock_settle.assert_awaited_once_with("mkt-1", "YES", db)
    assert result["outcome"] == "YES"
    assert result["cancelled_orders"] == 0


@pytest.mark.asyncio
async def test_resolve_with_open_orders_cancels_them() -> None:
    from src.pm_admin.application.service import AdminService
    db = AsyncMock()
    market_mock = MagicMock()
    market_mock.fetchone.return_value = MagicMock(status="ACTIVE", id="mkt-1")
    orders_mock = MagicMock()
    # Two open orders: one FUNDS, one YES_SHARES
    order1 = MagicMock(
        id="ord-1", user_id="user-1",
        frozen_amount=612, frozen_asset_type="FUNDS", remaining_quantity=10
    )
    order2 = MagicMock(
        id="ord-2", user_id="user-2",
        frozen_amount=10, frozen_asset_type="YES_SHARES", remaining_quantity=10
    )
    orders_mock.fetchall.return_value = [order1, order2]
    db.execute.side_effect = [market_mock, orders_mock] + [AsyncMock()] * 6
    with patch("src.pm_admin.application.service.settle_market"):
        svc = AdminService()
        result = await svc.resolve_market("mkt-1", "NO", db)
    assert result["cancelled_orders"] == 2


@pytest.mark.asyncio
async def test_resolve_non_active_market_raises() -> None:
    from src.pm_admin.application.service import AdminService
    from src.pm_common.errors import AppError
    db = AsyncMock()
    market_mock = MagicMock()
    market_mock.fetchone.return_value = MagicMock(status="SETTLED", id="mkt-1")
    db.execute.return_value = market_mock
    svc = AdminService()
    with pytest.raises(AppError) as exc_info:
        await svc.resolve_market("mkt-1", "YES", db)
    assert exc_info.value.http_status == 422


@pytest.mark.asyncio
async def test_resolve_missing_market_raises() -> None:
    from src.pm_admin.application.service import AdminService
    from src.pm_common.errors import AppError
    db = AsyncMock()
    market_mock = MagicMock()
    market_mock.fetchone.return_value = None
    db.execute.return_value = market_mock
    svc = AdminService()
    with pytest.raises(AppError) as exc_info:
        await svc.resolve_market("mkt-missing", "YES", db)
    assert exc_info.value.http_status == 404
