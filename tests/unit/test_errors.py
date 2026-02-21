"""Tests for pm_common.errors and pm_common.response."""

from src.pm_common.errors import (
    AppError,
    InsufficientBalanceError,
    MarketNotActiveError,
    MarketNotFoundError,
    OrderNotFoundError,
    SelfTradeError,
)
from src.pm_common.response import ApiResponse, error_response, success_response


class TestAppError:
    def test_base_error(self) -> None:
        err = AppError(code=9002, message="Internal error")
        assert err.code == 9002
        assert err.message == "Internal error"
        assert err.http_status == 500

    def test_custom_http_status(self) -> None:
        err = AppError(code=1001, message="Username taken", http_status=409)
        assert err.http_status == 409

    def test_is_exception(self) -> None:
        err = AppError(code=1001, message="test")
        assert isinstance(err, Exception)


class TestSpecificErrors:
    def test_insufficient_balance(self) -> None:
        err = InsufficientBalanceError(required=6500, available=3000)
        assert err.code == 2001
        assert err.http_status == 422
        assert "6500" in err.message
        assert "3000" in err.message

    def test_market_not_found(self) -> None:
        err = MarketNotFoundError("MKT-123")
        assert err.code == 3001
        assert err.http_status == 404

    def test_market_not_active(self) -> None:
        err = MarketNotActiveError("MKT-123")
        assert err.code == 3002
        assert err.http_status == 422

    def test_order_not_found(self) -> None:
        err = OrderNotFoundError("order-abc")
        assert err.code == 4004
        assert err.http_status == 404

    def test_self_trade(self) -> None:
        err = SelfTradeError()
        assert err.code == 4003
        assert err.http_status == 422


class TestApiResponse:
    def test_success(self) -> None:
        resp = success_response({"id": "abc"})
        assert resp.code == 0
        assert resp.message == "success"
        assert resp.data == {"id": "abc"}

    def test_error(self) -> None:
        resp = error_response(2001, "Insufficient balance")
        assert resp.code == 2001
        assert resp.message == "Insufficient balance"
        assert resp.data is None

    def test_serialization(self) -> None:
        resp = success_response({"price": 65})
        d = resp.model_dump()
        assert "code" in d
        assert "message" in d
        assert "data" in d
        assert "timestamp" in d
        assert "request_id" in d
