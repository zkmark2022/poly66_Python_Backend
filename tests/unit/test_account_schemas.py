"""Tests for pm_account Pydantic schemas and cursor utilities."""

import pytest
from pydantic import ValidationError

from src.pm_account.application.schemas import (
    DepositRequest,
    WithdrawRequest,
    cursor_decode,
    cursor_encode,
)


class TestDepositRequest:
    def test_valid(self) -> None:
        req = DepositRequest(amount_cents=10000)
        assert req.amount_cents == 10000

    def test_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DepositRequest(amount_cents=0)

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DepositRequest(amount_cents=-100)


class TestWithdrawRequest:
    def test_valid(self) -> None:
        req = WithdrawRequest(amount_cents=5000)
        assert req.amount_cents == 5000

    def test_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            WithdrawRequest(amount_cents=0)


class TestCursorUtils:
    def test_encode_decode_roundtrip(self) -> None:
        cursor = cursor_encode(12345)
        assert cursor_decode(cursor) == 12345

    def test_encode_produces_string(self) -> None:
        cursor = cursor_encode(1)
        assert isinstance(cursor, str)
        assert len(cursor) > 0

    def test_decode_invalid_returns_none(self) -> None:
        assert cursor_decode("not-valid-base64!!!") is None

    def test_decode_none_returns_none(self) -> None:
        assert cursor_decode(None) is None
