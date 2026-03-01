"""Tests for get_current_user dependency focusing on UUID/string type safety.

Covers:
- Valid UUID string sub claim resolves user correctly
- Malformed sub claim raises 401 (not an unhandled ValueError)
- Missing sub claim raises 401
- Disabled user raises AccountDisabledError
- AMM bot UUID string is accepted as a valid UUID (type conversion works)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException

from src.pm_gateway.auth.dependencies import get_current_user
from src.pm_gateway.user.db_models import UserModel

AMM_USER_STR = "00000000-0000-4000-a000-000000000001"
AMM_USER_UUID = UUID(AMM_USER_STR)

REGULAR_USER_STR = "12345678-1234-5678-1234-567812345678"
REGULAR_USER_UUID = UUID(REGULAR_USER_STR)


def _mock_db(user: object) -> AsyncMock:
    """Build an AsyncMock db that returns *user* from scalar_one_or_none()."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result
    return mock_db


def _make_user(uid: UUID, is_active: bool = True) -> UserModel:
    user = MagicMock(spec=UserModel)
    user.id = uid
    user.is_active = is_active
    return user


class TestUuidTypeSafety:
    async def test_valid_string_uuid_resolves_user(self) -> None:
        """A properly formatted UUID string sub claim should authenticate."""
        user = _make_user(REGULAR_USER_UUID)
        mock_db = _mock_db(user)
        with patch(
            "src.pm_gateway.auth.dependencies.decode_token",
            return_value={"sub": REGULAR_USER_STR, "type": "access"},
        ):
            result = await get_current_user(token="dummy", db=mock_db)
        assert result is user

    async def test_amm_uuid_string_resolves_user(self) -> None:
        """AMM bot UUID string must be accepted by the UUID() conversion."""
        amm_user = _make_user(AMM_USER_UUID)
        mock_db = _mock_db(amm_user)
        with patch(
            "src.pm_gateway.auth.dependencies.decode_token",
            return_value={"sub": AMM_USER_STR, "type": "access"},
        ):
            result = await get_current_user(token="dummy", db=mock_db)
        assert result is amm_user

    async def test_malformed_uuid_sub_raises_401(self) -> None:
        """A non-UUID sub claim must raise HTTP 401, not an unhandled ValueError."""
        mock_db = _mock_db(None)
        with patch(
            "src.pm_gateway.auth.dependencies.decode_token",
            return_value={"sub": "not-a-uuid", "type": "access"},
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token="dummy", db=mock_db)
        assert exc_info.value.status_code == 401

    async def test_missing_sub_raises_401(self) -> None:
        mock_db = _mock_db(None)
        with patch(
            "src.pm_gateway.auth.dependencies.decode_token",
            return_value={"type": "access"},
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token="dummy", db=mock_db)
        assert exc_info.value.status_code == 401

    async def test_user_not_found_raises_401(self) -> None:
        mock_db = _mock_db(None)
        with patch(
            "src.pm_gateway.auth.dependencies.decode_token",
            return_value={"sub": REGULAR_USER_STR, "type": "access"},
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token="dummy", db=mock_db)
        assert exc_info.value.status_code == 401

    async def test_disabled_user_raises_account_disabled(self) -> None:
        from src.pm_common.errors import AccountDisabledError

        user = _make_user(REGULAR_USER_UUID, is_active=False)
        mock_db = _mock_db(user)
        with patch(
            "src.pm_gateway.auth.dependencies.decode_token",
            return_value={"sub": REGULAR_USER_STR, "type": "access"},
        ):
            with pytest.raises(AccountDisabledError):
                await get_current_user(token="dummy", db=mock_db)
