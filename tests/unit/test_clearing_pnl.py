# tests/unit/test_clearing_pnl.py
"""Unit tests — clearing scenarios return (buy_pnl, sell_pnl)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pm_matching.domain.models import TradeResult


def _make_trade(**kwargs: object) -> TradeResult:
    return TradeResult(
        buy_order_id=str(kwargs.get("buy_order_id", "b1")),
        sell_order_id=str(kwargs.get("sell_order_id", "s1")),
        buy_user_id=str(kwargs.get("buy_user_id", "user-b")),
        sell_user_id=str(kwargs.get("sell_user_id", "user-s")),
        market_id=str(kwargs.get("market_id", "mkt-1")),
        price=int(kwargs.get("price", 60)),  # type: ignore[arg-type]
        quantity=int(kwargs.get("quantity", 10)),  # type: ignore[arg-type]
        buy_book_type=str(kwargs.get("buy_book_type", "NATIVE_BUY")),
        sell_book_type=str(kwargs.get("sell_book_type", "NATIVE_SELL")),
        buy_original_price=int(kwargs.get("buy_original_price", 60)),  # type: ignore[arg-type]
        maker_order_id=str(kwargs.get("maker_order_id", "s1")),
        taker_order_id=str(kwargs.get("taker_order_id", "b1")),
    )


@pytest.mark.asyncio
async def test_mint_returns_none_pnl() -> None:
    from src.pm_clearing.domain.scenarios.mint import clear_mint
    trade = _make_trade(buy_book_type="NATIVE_BUY", sell_book_type="SYNTHETIC_SELL")
    market = MagicMock()
    db = AsyncMock()
    result = await clear_mint(trade, market, db)
    assert result == (None, None)


@pytest.mark.asyncio
async def test_transfer_yes_returns_sell_pnl() -> None:
    from src.pm_clearing.domain.scenarios.transfer_yes import clear_transfer_yes
    trade = _make_trade(price=60, quantity=10)
    market = MagicMock()
    db = AsyncMock()
    # Mock: seller has yes_volume=10, yes_cost_sum=500, pending=10 (full close)
    result_mock = MagicMock()
    result_mock.fetchone.return_value = (10, 500, 10)
    db.execute.return_value = result_mock
    buy_pnl, sell_pnl = await clear_transfer_yes(trade, market, db)
    assert buy_pnl is None
    # proceeds = 60*10=600, cost_released=500 (full close), pnl=100
    assert sell_pnl == 100


@pytest.mark.asyncio
async def test_transfer_no_returns_buy_pnl() -> None:
    from src.pm_clearing.domain.scenarios.transfer_no import clear_transfer_no
    trade = _make_trade(price=60, quantity=10,
                        buy_book_type="SYNTHETIC_BUY", sell_book_type="SYNTHETIC_SELL")
    market = MagicMock()
    db = AsyncMock()
    # Mock first execute (UNFREEZE_DEBIT for sell_user) returns anything
    # Mock second execute (ADD_NO_VOLUME for sell_user) returns anything
    # Mock third execute (GET_BUYER_NO for buy_user) returns position row
    unfreeze_mock = MagicMock()
    unfreeze_mock.fetchone.return_value = None  # not used
    add_no_mock = MagicMock()
    add_no_mock.fetchone.return_value = None  # not used
    get_buyer_mock = MagicMock()
    get_buyer_mock.fetchone.return_value = (10, 400, 10)  # no_vol=10, no_cost=400, pending=10
    reduce_no_mock = MagicMock()
    reduce_no_mock.fetchone.return_value = None
    add_balance_mock = MagicMock()
    add_balance_mock.fetchone.return_value = None
    db.execute.side_effect = [
        unfreeze_mock, add_no_mock, get_buyer_mock, reduce_no_mock, add_balance_mock
    ]
    buy_pnl, sell_pnl = await clear_transfer_no(trade, market, db)
    assert sell_pnl is None
    # no_price = 40, proceeds = 400, cost_released = 400, pnl = 0
    assert buy_pnl == 0


@pytest.mark.asyncio
async def test_burn_returns_both_pnl() -> None:
    from src.pm_clearing.domain.scenarios.burn import clear_burn
    trade = _make_trade(price=70, quantity=5,
                        buy_book_type="SYNTHETIC_BUY", sell_book_type="NATIVE_SELL")
    market = MagicMock()
    db = AsyncMock()
    # get_yes: yes_vol=5, yes_cost=250, pending=5
    yes_pos_mock = MagicMock()
    yes_pos_mock.fetchone.return_value = (5, 250, 5)
    # get_no: no_vol=5, no_cost=150, pending=5
    no_pos_mock = MagicMock()
    no_pos_mock.fetchone.return_value = (5, 150, 5)
    # remaining executes (reduce_yes, add_balance_sell, reduce_no, add_balance_buy)
    dummy = MagicMock()
    dummy.fetchone.return_value = None
    db.execute.side_effect = [yes_pos_mock, no_pos_mock, dummy, dummy, dummy, dummy]
    buy_pnl, sell_pnl = await clear_burn(trade, market, db)
    # yes_proceeds=350, yes_cost_rel=250 → sell_pnl=100
    assert sell_pnl == 100
    # no_proceeds=150, no_cost_rel=150 → buy_pnl=0
    assert buy_pnl == 0
