"""Unit tests for JWT handler."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from jose import jwt

from src.pm_common.errors import InvalidCredentialsError, InvalidRefreshTokenError
from src.pm_gateway.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
)


def test_access_token_contains_correct_claims() -> None:
    token = create_access_token("user-123")
    # Decode without verification to inspect claims
    payload = jwt.get_unverified_claims(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_refresh_token_contains_correct_claims() -> None:
    token = create_refresh_token("user-123")
    payload = jwt.get_unverified_claims(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "refresh"


def test_decode_valid_access_token() -> None:
    token = create_access_token("user-abc")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-abc"
    assert payload["type"] == "access"


def test_decode_valid_refresh_token() -> None:
    token = create_refresh_token("user-abc")
    payload = decode_token(token, expected_type="refresh")
    assert payload["sub"] == "user-abc"
    assert payload["type"] == "refresh"


def test_access_token_used_as_refresh_raises_error() -> None:
    """Using access token where refresh is expected must fail."""
    token = create_access_token("user-abc")
    with pytest.raises(InvalidRefreshTokenError):
        decode_token(token, expected_type="refresh")


def test_refresh_token_used_as_access_raises_error() -> None:
    """Using refresh token where access is expected must fail."""
    token = create_refresh_token("user-abc")
    with pytest.raises(InvalidCredentialsError):
        decode_token(token, expected_type="access")


def test_expired_access_token_raises_credentials_error() -> None:
    """Expired access token must raise InvalidCredentialsError."""
    # Monkey-patch expiry to past
    with patch(
        "src.pm_gateway.auth.jwt_handler._ACCESS_EXPIRE",
        timedelta(seconds=-1),
    ):
        token = create_access_token("user-abc")
    with pytest.raises(InvalidCredentialsError):
        decode_token(token, expected_type="access")


def test_expired_refresh_token_raises_refresh_error() -> None:
    """Expired refresh token must raise InvalidRefreshTokenError."""
    with patch(
        "src.pm_gateway.auth.jwt_handler._REFRESH_EXPIRE",
        timedelta(seconds=-1),
    ):
        token = create_refresh_token("user-abc")
    with pytest.raises(InvalidRefreshTokenError):
        decode_token(token, expected_type="refresh")


def test_tampered_token_raises_error() -> None:
    """Tampered token signature must be rejected."""
    token = create_access_token("user-abc")
    tampered = token[:-4] + "xxxx"
    with pytest.raises(InvalidCredentialsError):
        decode_token(tampered, expected_type="access")
