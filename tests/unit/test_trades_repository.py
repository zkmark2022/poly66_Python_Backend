# tests/unit/test_trades_repository.py
"""Unit tests for TradesRepository."""
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_trade_row(**kwargs: Any) -> MagicMock:
    row = MagicMock()
    row.trade_id = kwargs.get("trade_id", "t1")
    row.market_id = kwargs.get("market_id", "mkt-1")
    row.scenario = kwargs.get("scenario", "MINT")
    row.buy_order_id = kwargs.get("buy_order_id", "b1")
    row.sell_order_id = kwargs.get("sell_order_id", "s1")
    row.buy_user_id = kwargs.get("buy_user_id", "user-b")
    row.sell_user_id = kwargs.get("sell_user_id", "user-s")
    row.buy_book_type = kwargs.get("buy_book_type", "NATIVE_BUY")
    row.sell_book_type = kwargs.get("sell_book_type", "SYNTHETIC_SELL")
    row.price = kwargs.get("price", 60)
    row.quantity = kwargs.get("quantity", 10)
    row.maker_order_id = kwargs.get("maker_order_id", "s1")
    row.taker_order_id = kwargs.get("taker_order_id", "b1")
    row.taker_fee = kwargs.get("taker_fee", 12)
    row.maker_fee = kwargs.get("maker_fee", 0)
    row.buy_realized_pnl = kwargs.get("buy_realized_pnl")
    row.sell_realized_pnl = kwargs.get("sell_realized_pnl")
    row.executed_at = kwargs.get("executed_at", datetime.now(UTC))
    return row


@pytest.mark.asyncio
async def test_list_by_user_returns_empty() -> None:
    from src.pm_clearing.infrastructure.trades_repository import TradesRepository
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = []
    db.execute.return_value = result_mock
    repo = TradesRepository()
    trades = await repo.list_by_user("user-1", None, 20, None, db)
    assert trades == []


@pytest.mark.asyncio
async def test_list_by_user_returns_rows() -> None:
    from src.pm_clearing.infrastructure.trades_repository import TradesRepository
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [
        _make_trade_row(),
        _make_trade_row(trade_id="t2"),
    ]
    db.execute.return_value = result_mock
    repo = TradesRepository()
    trades = await repo.list_by_user("user-b", None, 20, None, db)
    assert len(trades) == 2
    assert trades[0]["trade_id"] == "t1"
    assert trades[0]["price"] == 60


@pytest.mark.asyncio
async def test_list_by_user_with_market_filter() -> None:
    from src.pm_clearing.infrastructure.trades_repository import TradesRepository
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [_make_trade_row(market_id="mkt-specific")]
    db.execute.return_value = result_mock
    repo = TradesRepository()
    trades = await repo.list_by_user("user-b", "mkt-specific", 20, None, db)
    assert len(trades) == 1
    assert trades[0]["market_id"] == "mkt-specific"
