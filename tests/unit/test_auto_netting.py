from unittest.mock import AsyncMock, MagicMock

from src.pm_clearing.domain.netting import execute_netting_if_needed


class TestNetting:
    async def test_no_netting_when_no_both_sides(self) -> None:
        mock_db = AsyncMock()
        # yes=100 no=0: no netting
        fetch_mock = MagicMock()
        fetch_mock.fetchone.return_value = (100, 6500, 0, 0, 0, 0)
        mock_db.execute.return_value = fetch_mock
        market = MagicMock(reserve_balance=10000, pnl_pool=0)
        result = await execute_netting_if_needed("u1", "mkt-1", market, mock_db)
        assert result == 0

    async def test_netting_qty_excludes_pending_sell(self) -> None:
        # yes_volume=100, yes_pending_sell=80 → available_yes=20
        # no_volume=50, no_pending_sell=0 → available_no=50
        # nettable = min(20, 50) = 20
        mock_db = AsyncMock()
        fetch_mock = MagicMock()
        fetch_mock.fetchone.return_value = (100, 6500, 80, 50, 2500, 0)
        mock_db.execute.return_value = fetch_mock
        market = MagicMock(reserve_balance=20000, pnl_pool=500)
        result = await execute_netting_if_needed("u1", "mkt-1", market, mock_db)
        assert result == 20
