# tests/unit/test_batch_cancel.py
"""Test Batch Cancel logic. See interface contract v1.4 §3.2."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.pm_account.domain.constants import AMM_USER_ID


class TestBatchCancel:
    @pytest.mark.asyncio
    async def test_cancel_all_returns_count(self) -> None:
        """Cancel ALL scope should cancel all AMM orders in market."""
        from src.pm_matching.engine.engine import MatchingEngine

        engine = MatchingEngine()
        db = AsyncMock()

        # Mock: 3 active AMM orders
        mock_orders = MagicMock()
        mock_orders.fetchall.return_value = [
            MagicMock(
                id="o1", frozen_amount=1000, frozen_asset_type="FUNDS",
                original_direction="BUY", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
            MagicMock(
                id="o2", frozen_amount=500, frozen_asset_type="YES_SHARES",
                original_direction="SELL", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
            MagicMock(
                id="o3", frozen_amount=300, frozen_asset_type="NO_SHARES",
                original_direction="SELL", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
        ]
        db.execute.return_value = mock_orders

        result = await engine.batch_cancel(
            market_id="mkt-1",
            user_id=AMM_USER_ID,
            cancel_scope="ALL",
            db=db,
        )
        assert result["cancelled_count"] == 3

    @pytest.mark.asyncio
    async def test_cancel_no_active_orders(self) -> None:
        """No active orders → cancelled_count = 0, not an error."""
        from src.pm_matching.engine.engine import MatchingEngine

        engine = MatchingEngine()
        db = AsyncMock()

        mock_orders = MagicMock()
        mock_orders.fetchall.return_value = []
        db.execute.return_value = mock_orders

        result = await engine.batch_cancel(
            market_id="mkt-1",
            user_id=AMM_USER_ID,
            cancel_scope="ALL",
            db=db,
        )
        assert result["cancelled_count"] == 0

    @pytest.mark.asyncio
    async def test_cancel_buy_only_filters_correctly(self) -> None:
        """BUY_ONLY scope: cancel only BUY original_direction orders."""
        from src.pm_matching.engine.engine import MatchingEngine

        engine = MatchingEngine()
        db = AsyncMock()

        mock_orders = MagicMock()
        mock_orders.fetchall.return_value = [
            MagicMock(
                id="o1", frozen_amount=1000, frozen_asset_type="FUNDS",
                original_direction="BUY", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
            MagicMock(
                id="o2", frozen_amount=2000, frozen_asset_type="FUNDS",
                original_direction="BUY", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
        ]
        db.execute.return_value = mock_orders

        result = await engine.batch_cancel(
            market_id="mkt-1",
            user_id=AMM_USER_ID,
            cancel_scope="BUY_ONLY",
            db=db,
        )
        assert result["cancelled_count"] == 2

    @pytest.mark.asyncio
    async def test_cancel_all_unfrozen_amounts_summed(self) -> None:
        """All unfrozen amounts (funds, yes_shares, no_shares) are summed correctly."""
        from src.pm_matching.engine.engine import MatchingEngine

        engine = MatchingEngine()
        db = AsyncMock()

        mock_orders = MagicMock()
        mock_orders.fetchall.return_value = [
            MagicMock(
                id="o1", frozen_amount=1000, frozen_asset_type="FUNDS",
                original_direction="BUY", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
            MagicMock(
                id="o2", frozen_amount=50, frozen_asset_type="YES_SHARES",
                original_direction="SELL", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
            MagicMock(
                id="o3", frozen_amount=30, frozen_asset_type="NO_SHARES",
                original_direction="SELL", user_id=AMM_USER_ID, market_id="mkt-1",
            ),
        ]
        db.execute.return_value = mock_orders

        result = await engine.batch_cancel(
            market_id="mkt-1",
            user_id=AMM_USER_ID,
            cancel_scope="ALL",
            db=db,
        )
        assert result["total_unfrozen_funds_cents"] == 1000
        assert result["total_unfrozen_yes_shares"] == 50
        assert result["total_unfrozen_no_shares"] == 30
        assert result["market_id"] == "mkt-1"
