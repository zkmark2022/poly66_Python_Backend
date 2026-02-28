"""Unit tests for BURN scenario clearing: SYNTHETIC_BUY + NATIVE_SELL."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.pm_clearing.domain.scenarios.burn import clear_burn
from src.pm_matching.domain.models import TradeResult


def _trade(
    price: int = 65,
    qty: int = 100,
) -> TradeResult:
    return TradeResult(
        buy_order_id="bo1",
        sell_order_id="so1",
        buy_user_id="buyer",
        sell_user_id="seller",
        market_id="mkt-1",
        price=price,
        quantity=qty,
        buy_book_type="SYNTHETIC_BUY",
        sell_book_type="NATIVE_SELL",
        buy_original_price=100 - price,
        maker_order_id="so1",
        taker_order_id="bo1",
    )


def _make_db(
    yes_row: tuple = (500, 32500, 100),
    no_row: tuple = (500, 17500, 100),
    yes_balance_rowcount: int = 1,
    no_balance_rowcount: int = 1,
) -> AsyncMock:
    """Build a mock DB with sequential execute() return values."""
    mock_db = AsyncMock()

    yes_fetch = MagicMock()
    yes_fetch.fetchone.return_value = yes_row

    no_fetch = MagicMock()
    no_fetch.fetchone.return_value = no_row

    reduce_yes = MagicMock(rowcount=1)
    add_yes_balance = MagicMock(rowcount=yes_balance_rowcount)
    reduce_no = MagicMock(rowcount=1)
    add_no_balance = MagicMock(rowcount=no_balance_rowcount)

    mock_db.execute.side_effect = [
        yes_fetch,       # _GET_YES_POS_SQL
        no_fetch,        # _GET_NO_POS_SQL
        reduce_yes,      # _REDUCE_YES_VOLUME_SQL
        add_yes_balance, # _ADD_BALANCE_SQL (YES seller)
        reduce_no,       # _REDUCE_NO_VOLUME_SQL
        add_no_balance,  # _ADD_BALANCE_SQL (NO seller)
    ]
    return mock_db


def _market(
    total_yes_shares: int = 1000,
    total_no_shares: int = 1000,
    reserve_balance: int = 100000,
    pnl_pool: int = 0,
) -> MagicMock:
    return MagicMock(
        total_yes_shares=total_yes_shares,
        total_no_shares=total_no_shares,
        reserve_balance=reserve_balance,
        pnl_pool=pnl_pool,
    )


class TestClearBurn:
    async def test_market_total_yes_shares_decremented(self) -> None:
        trade = _trade(price=65, qty=100)
        market = _market()
        await clear_burn(trade, market, _make_db())
        assert market.total_yes_shares == 900

    async def test_market_total_no_shares_decremented(self) -> None:
        trade = _trade(price=65, qty=100)
        market = _market()
        await clear_burn(trade, market, _make_db())
        assert market.total_no_shares == 900

    async def test_market_reserve_balance_decremented(self) -> None:
        trade = _trade(price=65, qty=100)
        market = _market(reserve_balance=100000)
        await clear_burn(trade, market, _make_db())
        # payout_per_share=100, qty=100 → -10000
        assert market.reserve_balance == 90000

    async def test_yes_seller_credited_with_price_times_qty(self) -> None:
        trade = _trade(price=65, qty=100)
        market = _market()
        mock_db = _make_db()
        await clear_burn(trade, market, mock_db)
        # 4th execute call is _ADD_BALANCE_SQL for YES seller
        call_args = mock_db.execute.call_args_list[3]
        params = call_args[0][1]
        assert params["amount"] == 65 * 100  # price * qty
        assert params["user_id"] == "seller"

    async def test_no_seller_credited_with_complement_price(self) -> None:
        trade = _trade(price=65, qty=100)
        market = _market()
        mock_db = _make_db()
        await clear_burn(trade, market, mock_db)
        # 6th execute call is _ADD_BALANCE_SQL for NO seller
        call_args = mock_db.execute.call_args_list[5]
        params = call_args[0][1]
        assert params["amount"] == (100 - 65) * 100  # (100-price) * qty
        assert params["user_id"] == "buyer"

    async def test_returns_buy_and_sell_pnl(self) -> None:
        # yes_cost=32500, yes_vol=500, qty=100 → cost_rel=6500
        # yes_proceeds = 65 * 100 = 6500, sell_pnl = 6500 - 6500 = 0
        # no_cost=17500, no_vol=500, qty=100 → cost_rel=3500
        # no_proceeds = 35 * 100 = 3500, buy_pnl = 3500 - 3500 = 0
        trade = _trade(price=65, qty=100)
        market = _market()
        buy_pnl, sell_pnl = await clear_burn(trade, market, _make_db())
        assert sell_pnl == 0  # 6500 proceeds - 6500 cost_released
        assert buy_pnl == 0   # 3500 proceeds - 3500 cost_released

    async def test_raises_when_yes_position_not_found(self) -> None:
        trade = _trade()
        market = _market()
        mock_db = AsyncMock()
        no_row_result = MagicMock()
        no_row_result.fetchone.return_value = None
        mock_db.execute.return_value = no_row_result
        with pytest.raises(RuntimeError, match="Sell YES position not found"):
            await clear_burn(trade, market, mock_db)

    async def test_raises_when_no_position_not_found(self) -> None:
        trade = _trade()
        market = _market()
        mock_db = AsyncMock()
        yes_found = MagicMock()
        yes_found.fetchone.return_value = (500, 32500, 100)
        not_found = MagicMock()
        not_found.fetchone.return_value = None
        mock_db.execute.side_effect = [yes_found, not_found]
        with pytest.raises(RuntimeError, match="Sell NO position not found"):
            await clear_burn(trade, market, mock_db)

    async def test_raises_when_yes_seller_account_missing(self) -> None:
        trade = _trade()
        market = _market()
        mock_db = _make_db(yes_balance_rowcount=0)
        with pytest.raises(RuntimeError, match="Account not found for YES seller"):
            await clear_burn(trade, market, mock_db)

    async def test_raises_when_no_seller_account_missing(self) -> None:
        trade = _trade()
        market = _market()
        mock_db = _make_db(no_balance_rowcount=0)
        with pytest.raises(RuntimeError, match="Account not found for NO seller"):
            await clear_burn(trade, market, mock_db)
