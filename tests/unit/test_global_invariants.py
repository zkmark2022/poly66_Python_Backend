# tests/unit/test_global_invariants.py
"""Unit tests for global invariant checks."""
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_verify_global_balanced_returns_empty() -> None:
    from src.pm_clearing.domain.global_invariants import verify_global_invariants
    db = AsyncMock()
    # user_balance=1000, market_reserve=200, platform_fee=50 → total=1250
    # net_deposits=1250 → balanced
    balance_row = MagicMock()
    balance_row.scalar_one.return_value = 1000
    reserve_row = MagicMock()
    reserve_row.scalar_one.return_value = 200
    platform_row = MagicMock()
    platform_row.scalar_one.return_value = 50
    deposit_row = MagicMock()
    deposit_row.scalar_one.return_value = 1250
    db.execute.side_effect = [balance_row, reserve_row, platform_row, deposit_row]
    violations = await verify_global_invariants(db)
    assert violations == []


@pytest.mark.asyncio
async def test_verify_global_imbalanced_returns_violation() -> None:
    from src.pm_clearing.domain.global_invariants import verify_global_invariants
    db = AsyncMock()
    balance_row = MagicMock()
    balance_row.scalar_one.return_value = 1000
    reserve_row = MagicMock()
    reserve_row.scalar_one.return_value = 200
    platform_row = MagicMock()
    platform_row.scalar_one.return_value = 50
    deposit_row = MagicMock()
    deposit_row.scalar_one.return_value = 1300  # mismatch: 50 too much
    db.execute.side_effect = [balance_row, reserve_row, platform_row, deposit_row]
    violations = await verify_global_invariants(db)
    assert len(violations) == 1
    assert "INV-G" in violations[0]
