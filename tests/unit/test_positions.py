# tests/unit/test_positions.py
"""Unit tests for positions infrastructure."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_pos_row(**kwargs: Any) -> MagicMock:
    row = MagicMock()
    row.market_id = kwargs.get("market_id", "mkt-1")
    row.yes_volume = kwargs.get("yes_volume", 10)
    row.yes_cost_sum = kwargs.get("yes_cost_sum", 600)
    row.no_volume = kwargs.get("no_volume", 0)
    row.no_cost_sum = kwargs.get("no_cost_sum", 0)
    return row


@pytest.mark.asyncio
async def test_list_positions_returns_rows() -> None:
    from src.pm_account.infrastructure.positions_repository import PositionsRepository
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [
        _make_pos_row(),
        _make_pos_row(market_id="mkt-2", yes_volume=5),
    ]
    db.execute.return_value = result_mock
    repo = PositionsRepository()
    positions = await repo.list_by_user("user-1", db)
    assert len(positions) == 2
    assert positions[0]["market_id"] == "mkt-1"
    assert positions[0]["yes_volume"] == 10


@pytest.mark.asyncio
async def test_list_positions_returns_empty() -> None:
    from src.pm_account.infrastructure.positions_repository import PositionsRepository
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = []
    db.execute.return_value = result_mock
    repo = PositionsRepository()
    positions = await repo.list_by_user("user-1", db)
    assert positions == []


@pytest.mark.asyncio
async def test_get_position_returns_none_when_missing() -> None:
    from src.pm_account.infrastructure.positions_repository import PositionsRepository
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchone.return_value = None
    db.execute.return_value = result_mock
    repo = PositionsRepository()
    pos = await repo.get_by_market("user-1", "mkt-missing", db)
    assert pos is None


@pytest.mark.asyncio
async def test_get_position_returns_data_when_found() -> None:
    from src.pm_account.infrastructure.positions_repository import PositionsRepository
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchone.return_value = _make_pos_row(yes_volume=5, yes_cost_sum=300)
    db.execute.return_value = result_mock
    repo = PositionsRepository()
    pos = await repo.get_by_market("user-1", "mkt-1", db)
    assert pos is not None
    assert pos["yes_volume"] == 5
    assert pos["yes_cost_sum"] == 300
