"""Unit tests for user service (mocked DB)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pm_common.errors import (
    AccountDisabledError,
    EmailExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    UsernameExistsError,
)
from src.pm_gateway.user.db_models import UserModel
from src.pm_gateway.user.service import UserService


def _make_user(is_active: bool = True) -> UserModel:
    user = UserModel()
    user.id = uuid.uuid4()
    user.username = "alice"
    user.email = "alice@example.com"
    user.password_hash = "$2b$12$fakehash"
    user.is_active = is_active
    return user


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service() -> UserService:
    return UserService()


class TestRegister:
    async def test_duplicate_username_raises_error(
        self, service: UserService, mock_db: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_user()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(UsernameExistsError):
            await service.register("alice", "new@email.com", "Pass1word", mock_db)

    async def test_duplicate_email_raises_error(
        self, service: UserService, mock_db: AsyncMock
    ) -> None:
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        mock_found = MagicMock()
        mock_found.scalar_one_or_none.return_value = _make_user()
        mock_db.execute = AsyncMock(side_effect=[mock_none, mock_found])

        with pytest.raises(EmailExistsError):
            await service.register("newuser", "alice@example.com", "Pass1word", mock_db)


class TestLogin:
    async def test_wrong_username_raises_credentials_error(
        self, service: UserService, mock_db: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(InvalidCredentialsError):
            await service.login("nobody", "Pass1word", mock_db)

    async def test_wrong_password_raises_credentials_error(
        self, service: UserService, mock_db: AsyncMock
    ) -> None:
        user = _make_user()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch("src.pm_gateway.user.service.verify_password", return_value=False),
            pytest.raises(InvalidCredentialsError),
        ):
            await service.login("alice", "WrongPass1", mock_db)

    async def test_disabled_account_raises_error(
        self, service: UserService, mock_db: AsyncMock
    ) -> None:
        user = _make_user(is_active=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch("src.pm_gateway.user.service.verify_password", return_value=True),
            pytest.raises(AccountDisabledError),
        ):
            await service.login("alice", "Pass1word", mock_db)

    async def test_success_returns_token_pair(
        self, service: UserService, mock_db: AsyncMock
    ) -> None:
        user = _make_user()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.pm_gateway.user.service.verify_password", return_value=True):
            returned_user, access, refresh = await service.login("alice", "Pass1word", mock_db)

        assert returned_user.username == "alice"
        assert len(access) > 20
        assert len(refresh) > 20
        assert access != refresh


class TestRefresh:
    async def test_invalid_refresh_token_raises_error(self, service: UserService) -> None:
        with pytest.raises(InvalidRefreshTokenError):
            await service.refresh("not.a.real.token")

    async def test_access_token_used_as_refresh_raises_error(self, service: UserService) -> None:
        from src.pm_gateway.auth.jwt_handler import create_access_token

        access = create_access_token("user-123")
        with pytest.raises(InvalidRefreshTokenError):
            await service.refresh(access)
