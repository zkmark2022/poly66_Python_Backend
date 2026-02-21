"""Unit tests for pm_gateway Pydantic schemas."""

import pytest
from pydantic import ValidationError

from src.pm_gateway.user.schemas import RegisterRequest


class TestRegisterRequest:
    def test_valid_input(self) -> None:
        req = RegisterRequest(
            username="alice",
            email="alice@example.com",
            password="SecureP@ss1",
        )
        assert req.username == "alice"

    def test_username_too_short(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(username="ab", email="a@b.com", password="SecureP@ss1")

    def test_username_too_long(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="a" * 65, email="a@b.com", password="SecureP@ss1"
            )

    def test_username_invalid_chars(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="alice!", email="a@b.com", password="SecureP@ss1"
            )

    def test_invalid_email(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="alice", email="not-an-email", password="SecureP@ss1"
            )

    def test_password_too_short(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(username="alice", email="a@b.com", password="Ab1")

    def test_password_no_uppercase(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="alice", email="a@b.com", password="alllower1"
            )

    def test_password_no_lowercase(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="alice", email="a@b.com", password="ALLUPPER1"
            )

    def test_password_no_digit(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="alice", email="a@b.com", password="NoDigitPass"
            )
