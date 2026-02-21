# tests/unit/test_market_state.py
"""Unit tests for MarketState construction."""
from typing import Any
from unittest.mock import MagicMock

from src.pm_matching.engine.engine import MarketState


def _make_row(**kwargs: Any) -> MagicMock:
    row = MagicMock()
    row.id = kwargs.get("id", "mkt-1")
    row.status = kwargs.get("status", "ACTIVE")
    row.reserve_balance = kwargs.get("reserve_balance", 0)
    row.pnl_pool = kwargs.get("pnl_pool", 0)
    row.total_yes_shares = kwargs.get("total_yes_shares", 0)
    row.total_no_shares = kwargs.get("total_no_shares", 0)
    row.taker_fee_bps = kwargs.get("taker_fee_bps", 20)
    return row


def test_market_state_reads_taker_fee_bps() -> None:
    row = _make_row(taker_fee_bps=15)
    ms = MarketState(row)
    assert ms.taker_fee_bps == 15


def test_market_state_default_fields() -> None:
    row = _make_row()
    ms = MarketState(row)
    assert ms.id == "mkt-1"
    assert ms.status == "ACTIVE"
    assert ms.taker_fee_bps == 20
