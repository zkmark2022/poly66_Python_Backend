# tests/unit/test_admin_stats.py
"""Unit tests for AdminService.get_market_stats."""
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_get_market_stats_returns_aggregates() -> None:
    from src.pm_admin.application.service import AdminService
    db = AsyncMock()
    market_mock = MagicMock()
    market_mock.fetchone.return_value = MagicMock(status="ACTIVE", id="mkt-1")
    stats_mock = MagicMock()
    stats_row = MagicMock()
    stats_row.total_trades = 5
    stats_row.total_volume = 100
    stats_row.total_fees = 12
    stats_row.unique_traders = 3
    stats_mock.fetchone.return_value = stats_row
    db.execute.side_effect = [market_mock, stats_mock]
    svc = AdminService()
    result = await svc.get_market_stats("mkt-1", db)
    assert result["total_trades"] == 5
    assert result["total_volume"] == 100
    assert result["total_fees"] == 12
    assert result["unique_traders"] == 3
    assert result["market_id"] == "mkt-1"
    assert result["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_get_market_stats_raises_when_not_found() -> None:
    from src.pm_admin.application.service import AdminService
    from src.pm_common.errors import AppError
    db = AsyncMock()
    market_mock = MagicMock()
    market_mock.fetchone.return_value = None
    db.execute.return_value = market_mock
    svc = AdminService()
    with pytest.raises(AppError) as exc_info:
        await svc.get_market_stats("mkt-missing", db)
    assert exc_info.value.http_status == 404
