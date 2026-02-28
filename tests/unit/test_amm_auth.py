"""Unit tests for require_amm_user FastAPI dependency."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.pm_account.domain.constants import AMM_USER_ID


class TestRequireAmmUser:
    @pytest.mark.asyncio
    async def test_amm_user_passes(self) -> None:
        from src.pm_gateway.auth.dependencies import require_amm_user

        mock_user = MagicMock()
        mock_user.id = uuid.UUID(AMM_USER_ID)

        result = await require_amm_user(current_user=mock_user)
        assert str(result.id) == AMM_USER_ID

    @pytest.mark.asyncio
    async def test_non_amm_user_rejected(self) -> None:
        from src.pm_gateway.auth.dependencies import require_amm_user

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        with pytest.raises(HTTPException) as exc_info:
            await require_amm_user(current_user=mock_user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_amm_user_id_string_comparison(self) -> None:
        """Ensure str() conversion prevents UUID vs str type mismatch."""
        from src.pm_gateway.auth.dependencies import require_amm_user

        mock_user = MagicMock()
        # id is a uuid.UUID object, not a string — this is the real-world case
        mock_user.id = uuid.UUID(AMM_USER_ID)

        result = await require_amm_user(current_user=mock_user)
        assert result is mock_user
