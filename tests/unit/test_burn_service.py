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


"""Test privileged burn business logic. See interface contract v1.4 §3.4."""


class TestPrivilegedBurn:
    @pytest.mark.asyncio
    async def test_burn_success_recovers_cash(self) -> None:
        """Burn 200 shares recovers 20000 cents (200 × 100)."""
        from src.pm_clearing.domain.burn_service import execute_privileged_burn
        from src.pm_account.domain.constants import AMM_USER_ID

        db = AsyncMock()
        db.execute.side_effect = self._mock_burn_db_calls(
            idempotent_exists=False,
            market_status="ACTIVE",
            yes_volume=1000,
            no_volume=1000,
            yes_pending_sell=0,
            no_pending_sell=0,
        )

        result = await execute_privileged_burn(
            user_id=AMM_USER_ID,
            market_id="mkt-1",
            quantity=200,
            idempotency_key="burn-001",
            db=db,
        )
        assert result["recovered_cents"] == 20000
        assert result["burned_quantity"] == 200

    @pytest.mark.asyncio
    async def test_burn_insufficient_yes_shares_raises(self) -> None:
        """Not enough YES shares should raise AppError code 5001."""
        from src.pm_clearing.domain.burn_service import execute_privileged_burn
        from src.pm_account.domain.constants import AMM_USER_ID
        from src.pm_common.errors import AppError

        db = AsyncMock()
        db.execute.side_effect = self._mock_burn_db_calls(
            idempotent_exists=False,
            market_status="ACTIVE",
            yes_volume=100,  # only 100, need 200
            no_volume=1000,
            yes_pending_sell=0,
            no_pending_sell=0,
        )

        with pytest.raises(AppError) as exc_info:
            await execute_privileged_burn(
                user_id=AMM_USER_ID,
                market_id="mkt-1",
                quantity=200,
                idempotency_key="burn-002",
                db=db,
            )
        assert exc_info.value.code == 5001

    @pytest.mark.asyncio
    async def test_burn_respects_pending_sell(self) -> None:
        """Available = volume - pending_sell. Should fail if available < quantity."""
        from src.pm_clearing.domain.burn_service import execute_privileged_burn
        from src.pm_account.domain.constants import AMM_USER_ID
        from src.pm_common.errors import AppError

        db = AsyncMock()
        db.execute.side_effect = self._mock_burn_db_calls(
            idempotent_exists=False,
            market_status="ACTIVE",
            yes_volume=500,
            no_volume=500,
            yes_pending_sell=400,  # available = 100, need 200
            no_pending_sell=0,
        )

        with pytest.raises(AppError) as exc_info:
            await execute_privileged_burn(
                user_id=AMM_USER_ID,
                market_id="mkt-1",
                quantity=200,
                idempotency_key="burn-003",
                db=db,
            )
        assert exc_info.value.code == 5001

    @pytest.mark.asyncio
    async def test_burn_idempotent(self) -> None:
        from src.pm_clearing.domain.burn_service import execute_privileged_burn
        from src.pm_account.domain.constants import AMM_USER_ID

        db = AsyncMock()
        db.execute.side_effect = self._mock_burn_db_calls(idempotent_exists=True)

        result = await execute_privileged_burn(
            user_id=AMM_USER_ID,
            market_id="mkt-1",
            quantity=200,
            idempotency_key="burn-001",
            db=db,
        )
        assert result.get("idempotent_hit") is True

    @staticmethod
    def _mock_burn_db_calls(**kwargs):
        calls = []
        if kwargs.get("idempotent_exists"):
            mock_result = MagicMock()
            mock_result.fetchone.return_value = MagicMock(
                amount=20000, reference_id="burn-001"
            )
            calls.append(mock_result)
        else:
            # Idempotency check: not found
            mock_idem = MagicMock()
            mock_idem.fetchone.return_value = None
            calls.append(mock_idem)

            # Market status check
            mock_market = MagicMock()
            mock_market.fetchone.return_value = MagicMock(
                status=kwargs.get("market_status", "ACTIVE")
            )
            calls.append(mock_market)

            # Position check
            mock_pos = MagicMock()
            mock_pos.fetchone.return_value = MagicMock(
                yes_volume=kwargs.get("yes_volume", 0),
                no_volume=kwargs.get("no_volume", 0),
                yes_pending_sell=kwargs.get("yes_pending_sell", 0),
                no_pending_sell=kwargs.get("no_pending_sell", 0),
                yes_cost_sum=kwargs.get("yes_volume", 0) * 50,
                no_cost_sum=kwargs.get("no_volume", 0) * 50,
            )
            calls.append(mock_pos)

            # Subsequent UPDATE/INSERT calls
            for _ in range(10):
                mock_op = MagicMock()
                mock_op.rowcount = 1
                calls.append(mock_op)

        return calls
