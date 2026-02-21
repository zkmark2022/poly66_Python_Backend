import pytest
from unittest.mock import AsyncMock, MagicMock

from src.pm_clearing.domain.invariants import verify_invariants_after_trade


class TestInvariants:
    async def test_passes_when_all_ok(self) -> None:
        market = MagicMock(total_yes_shares=100, total_no_shares=100,
                           reserve_balance=10000, pnl_pool=500)
        mock_db = AsyncMock()
        fetch_mock = MagicMock()
        fetch_mock.scalar_one.return_value = 10500
        mock_db.execute.return_value = fetch_mock
        await verify_invariants_after_trade(market, mock_db)  # no exception

    async def test_inv1_fail_raises(self) -> None:
        market = MagicMock(total_yes_shares=100, total_no_shares=99,
                           reserve_balance=10000, pnl_pool=0)
        mock_db = AsyncMock()
        with pytest.raises(AssertionError, match=r"INV-1"):
            await verify_invariants_after_trade(market, mock_db)
