"""Unit tests for pm_clearing.infrastructure.ledger helpers."""
from unittest.mock import AsyncMock

import pytest

from src.pm_clearing.infrastructure.ledger import write_ledger, write_wal_event

pytestmark = pytest.mark.asyncio


class TestWriteLedger:
    async def test_executes_insert(self) -> None:
        mock_db = AsyncMock()
        await write_ledger(
            user_id="u1",
            entry_type="MINT_COST",
            amount=-6500,
            balance_after=93500,
            reference_type="TRADE",
            reference_id="t1",
            db=mock_db,
        )
        mock_db.execute.assert_called_once()


class TestWriteWalEvent:
    async def test_executes_insert(self) -> None:
        mock_db = AsyncMock()
        await write_wal_event(
            event_type="ORDER_ACCEPTED",
            order_id="o1",
            market_id="mkt-1",
            user_id="u1",
            payload={},
            db=mock_db,
        )
        mock_db.execute.assert_called_once()
