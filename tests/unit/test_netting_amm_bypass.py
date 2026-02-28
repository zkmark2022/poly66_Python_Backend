"""Test that execute_netting_if_needed skips AMM account."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.pm_account.domain.constants import AMM_USER_ID


class TestNettingAMMBypass:
    @pytest.mark.asyncio
    async def test_amm_user_skips_netting(self) -> None:
        """AMM account (auto_netting_enabled=false) should skip netting entirely."""
        from src.pm_clearing.domain.netting import execute_netting_if_needed

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        db.execute.return_value = mock_result

        result = await execute_netting_if_needed(AMM_USER_ID, "mkt-1", MagicMock(), db)
        assert result == 0  # No netting performed

    @pytest.mark.asyncio
    async def test_normal_user_proceeds_with_netting(self) -> None:
        """Normal user (auto_netting_enabled=true) should proceed with netting."""
        from src.pm_clearing.domain.netting import execute_netting_if_needed

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        db.execute.return_value = mock_result

        with patch(
            "src.pm_clearing.domain.netting._do_netting", new_callable=AsyncMock
        ) as mock_do:
            mock_do.return_value = 5
            result = await execute_netting_if_needed(
                "normal-user-id", "mkt-1", MagicMock(), db
            )
            assert mock_do.called

    @pytest.mark.asyncio
    async def test_netting_bypass_no_db_column_found(self) -> None:
        """If auto_netting_enabled lookup returns None (no row), treat as enabled (fail-safe)."""
        from src.pm_clearing.domain.netting import execute_netting_if_needed

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None  # no account row
        db.execute.return_value = mock_result

        with patch(
            "src.pm_clearing.domain.netting._do_netting", new_callable=AsyncMock
        ) as mock_do:
            mock_do.return_value = 0
            await execute_netting_if_needed("unknown-user", "mkt-1", MagicMock(), db)
            assert mock_do.called
