"""Unit tests for fee collection helpers."""
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_collect_fee_from_frozen_executes_two_updates() -> None:
    from src.pm_clearing.infrastructure.fee_collector import collect_fee_from_frozen

    db = AsyncMock()
    await collect_fee_from_frozen("user-1", actual_fee=10, max_fee=20, db=db)
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_collect_fee_from_proceeds_executes_two_updates() -> None:
    from src.pm_clearing.infrastructure.fee_collector import collect_fee_from_proceeds

    db = AsyncMock()
    await collect_fee_from_proceeds("user-1", actual_fee=10, db=db)
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_write_trade_executes_insert() -> None:
    from src.pm_clearing.infrastructure.trades_writer import write_trade
    from src.pm_matching.domain.models import TradeResult

    db = AsyncMock()
    trade = TradeResult(
        buy_order_id="b1",
        sell_order_id="s1",
        buy_user_id="user-b",
        sell_user_id="user-s",
        market_id="mkt-1",
        price=60,
        quantity=10,
        buy_book_type="NATIVE_BUY",
        sell_book_type="NATIVE_SELL",
        buy_original_price=60,
        maker_order_id="s1",
        taker_order_id="b1",
    )
    await write_trade(
        trade,
        scenario="TRANSFER_YES",
        maker_fee=0,
        taker_fee=12,
        buy_pnl=None,
        sell_pnl=100,
        db=db,
    )
    db.execute.assert_awaited_once()
