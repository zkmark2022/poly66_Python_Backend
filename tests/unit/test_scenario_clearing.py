"""Unit tests for pm_clearing scenario handlers and dispatcher."""
from unittest.mock import AsyncMock, MagicMock

from src.pm_clearing.domain.scenarios.mint import clear_mint
from src.pm_clearing.domain.scenarios.transfer_yes import clear_transfer_yes
from src.pm_clearing.domain.service import settle_trade
from src.pm_matching.domain.models import TradeResult


def _trade(
    buy_type: str = "NATIVE_BUY",
    sell_type: str = "SYNTHETIC_SELL",
    price: int = 65,
    qty: int = 100,
    buy_orig: int = 65,
) -> TradeResult:
    return TradeResult(
        buy_order_id="bo1",
        sell_order_id="so1",
        buy_user_id="buyer",
        sell_user_id="seller",
        market_id="mkt-1",
        price=price,
        quantity=qty,
        buy_book_type=buy_type,
        sell_book_type=sell_type,
        buy_original_price=buy_orig,
        maker_order_id="so1",
        taker_order_id="bo1",
    )


class TestClearMint:
    async def test_reserve_increases_by_100_per_share(self) -> None:
        trade = _trade("NATIVE_BUY", "SYNTHETIC_SELL", price=65, qty=100)
        market = MagicMock(
            reserve_balance=0, total_yes_shares=0, total_no_shares=0, pnl_pool=0
        )
        mock_db = AsyncMock()
        await clear_mint(trade, market, mock_db)
        assert market.reserve_balance == 10000  # 100 x 100
        assert market.total_yes_shares == 100
        assert market.total_no_shares == 100


class TestClearTransferYes:
    async def test_reserve_unchanged(self) -> None:
        trade = _trade("NATIVE_BUY", "NATIVE_SELL", price=65, qty=100)
        market = MagicMock(
            reserve_balance=10000, total_yes_shares=100, total_no_shares=100, pnl_pool=0
        )
        mock_db = AsyncMock()
        # seller position mock: (vol, cost, pending)
        # Use MagicMock for execute's return so fetchone() is a synchronous call
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (100, 6500, 0)
        mock_db.execute.return_value = mock_result
        await clear_transfer_yes(trade, market, mock_db)
        assert market.reserve_balance == 10000  # unchanged


class TestSettleTrade:
    async def test_dispatches_to_mint(self) -> None:
        trade = _trade("NATIVE_BUY", "SYNTHETIC_SELL")
        market = MagicMock(
            reserve_balance=0, total_yes_shares=0, total_no_shares=0, pnl_pool=0
        )
        mock_db = AsyncMock()
        # Should not raise — basic dispatch check
        await settle_trade(trade, market, mock_db, fee_bps=20)
