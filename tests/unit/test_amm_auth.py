"""Test AMM-only endpoint authentication dependency."""
import pytest
from unittest.mock import MagicMock
from src.pm_account.domain.constants import AMM_USER_ID


class TestRequireAMMUser:
    @pytest.mark.asyncio
    async def test_amm_user_passes(self) -> None:
        from src.pm_gateway.auth.dependencies import require_amm_user

        mock_user = MagicMock()
        mock_user.id = AMM_USER_ID
        # Should return the user without raising
        result = await require_amm_user(current_user=mock_user)
        assert result.id == AMM_USER_ID

    @pytest.mark.asyncio
    async def test_non_amm_user_rejected(self) -> None:
        from src.pm_gateway.auth.dependencies import require_amm_user
        from src.pm_common.errors import AppError

        mock_user = MagicMock()
        mock_user.id = "normal-user-id"
        with pytest.raises(AppError) as exc_info:
            await require_amm_user(current_user=mock_user)
        assert exc_info.value.http_status == 403
