"""Unit tests — ORDER_FREEZE and ORDER_UNFREEZE ledger entries are written."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pm_order.domain.models import Order


def _make_order(**kwargs: Any) -> Order:
    return Order(
        id=str(kwargs.get("id", "ord-1")),
        client_order_id=str(kwargs.get("client_order_id", "c1")),
        market_id=str(kwargs.get("market_id", "mkt-1")),
        user_id=str(kwargs.get("user_id", "user-1")),
        original_side=str(kwargs.get("original_side", "YES")),
        original_direction=str(kwargs.get("original_direction", "BUY")),
        original_price=int(kwargs.get("original_price", 60)),
        book_type=str(kwargs.get("book_type", "NATIVE_BUY")),
        book_direction=str(kwargs.get("book_direction", "BUY")),
        book_price=int(kwargs.get("book_price", 60)),
        quantity=int(kwargs.get("quantity", 10)),
        frozen_amount=int(kwargs.get("frozen_amount", 612)),
        frozen_asset_type=str(kwargs.get("frozen_asset_type", "FUNDS")),
        time_in_force=str(kwargs.get("time_in_force", "GTC")),
        status=str(kwargs.get("status", "OPEN")),
    )


@pytest.mark.asyncio
async def test_check_and_freeze_writes_order_freeze_ledger() -> None:
    from src.pm_risk.rules.balance_check import check_and_freeze

    db = AsyncMock()
    # Mock successful freeze (RETURNING returns a row)
    result_mock = MagicMock()
    result_mock.fetchone.return_value = MagicMock()  # row exists = freeze succeeded
    db.execute.return_value = result_mock
    order = _make_order()
    with patch("src.pm_risk.rules.balance_check.write_ledger") as mock_ledger:
        await check_and_freeze(order, db)
    mock_ledger.assert_awaited_once()
    args = mock_ledger.call_args
    assert args.kwargs["entry_type"] == "ORDER_FREEZE"
    assert args.kwargs["reference_type"] == "ORDER"
    assert args.kwargs["reference_id"] == order.id


@pytest.mark.asyncio
async def test_check_and_freeze_no_ledger_for_shares_order() -> None:
    """NATIVE_SELL (shares) order does not write a ledger entry."""
    from src.pm_risk.rules.balance_check import check_and_freeze

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchone.return_value = MagicMock()
    db.execute.return_value = result_mock
    order = _make_order(book_type="NATIVE_SELL", frozen_asset_type="YES_SHARES")
    with patch("src.pm_risk.rules.balance_check.write_ledger") as mock_ledger:
        await check_and_freeze(order, db)
    mock_ledger.assert_not_awaited()


@pytest.mark.asyncio
async def test_unfreeze_remainder_writes_order_unfreeze_ledger() -> None:
    from src.pm_matching.engine.engine import MatchingEngine

    engine = MatchingEngine()
    db = AsyncMock()
    order = _make_order(frozen_asset_type="FUNDS", frozen_amount=612, remaining_quantity=10)
    with patch("src.pm_matching.engine.engine.write_ledger") as mock_ledger:
        await engine._unfreeze_remainder(order, db)
    mock_ledger.assert_awaited_once()
    args = mock_ledger.call_args
    assert args.kwargs["entry_type"] == "ORDER_UNFREEZE"
    assert args.kwargs["reference_type"] == "ORDER"
    assert args.kwargs["reference_id"] == order.id


@pytest.mark.asyncio
async def test_unfreeze_remainder_no_ledger_for_shares_order() -> None:
    """YES_SHARES unfreeze does not write a ledger entry."""
    from src.pm_matching.engine.engine import MatchingEngine

    engine = MatchingEngine()
    db = AsyncMock()
    order = _make_order(
        frozen_asset_type="YES_SHARES",
        frozen_amount=10,
        remaining_quantity=10,
        market_id="mkt-1",
    )
    with patch("src.pm_matching.engine.engine.write_ledger") as mock_ledger:
        await engine._unfreeze_remainder(order, db)
    mock_ledger.assert_not_awaited()
