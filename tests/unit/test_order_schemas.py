"""Unit tests for pm_order Pydantic schemas."""
import pytest
from pydantic import ValidationError

from src.pm_order.application.schemas import PlaceOrderRequest


class TestPlaceOrderRequest:
    def test_valid_request(self) -> None:
        req = PlaceOrderRequest(
            client_order_id="abc", market_id="m1",
            side="YES", direction="BUY", price_cents=65, quantity=100
        )
        assert req.time_in_force == "GTC"

    def test_whitespace_in_client_order_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            PlaceOrderRequest(
                client_order_id="has space", market_id="m1",
                side="YES", direction="BUY", price_cents=65, quantity=100
            )

    def test_leading_whitespace_raises(self) -> None:
        with pytest.raises(ValidationError):
            PlaceOrderRequest(
                client_order_id=" leading", market_id="m1",
                side="YES", direction="BUY", price_cents=65, quantity=100
            )

    def test_empty_client_order_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            PlaceOrderRequest(
                client_order_id="", market_id="m1",
                side="YES", direction="BUY", price_cents=65, quantity=100
            )

    def test_ioc_time_in_force(self) -> None:
        req = PlaceOrderRequest(
            client_order_id="abc", market_id="m1",
            side="NO", direction="SELL", price_cents=35, quantity=50,
            time_in_force="IOC"
        )
        assert req.time_in_force == "IOC"

    def test_invalid_side_raises(self) -> None:
        with pytest.raises(ValidationError):
            PlaceOrderRequest(
                client_order_id="abc", market_id="m1",
                side="MAYBE", direction="BUY", price_cents=65, quantity=100  # type: ignore[arg-type]
            )
