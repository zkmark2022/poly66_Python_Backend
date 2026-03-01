"""Test privileged mint business logic. See interface contract v1.4 §3.3."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.pm_account.domain.constants import AMM_USER_ID


class TestPrivilegedMint:
    @pytest.mark.asyncio
    async def test_mint_success_deducts_balance(self) -> None:
        """Mint 1000 shares costs 100000 cents (1000 × 100)."""
        from src.pm_clearing.domain.mint_service import execute_privileged_mint

        db = AsyncMock()
        db.execute.side_effect = self._mock_mint_db_calls(
            idempotent_exists=False,
            market_status="ACTIVE",
            available_balance=500000,
            version=1,
        )

        result = await execute_privileged_mint(
            user_id=AMM_USER_ID,
            market_id="mkt-1",
            quantity=1000,
            idempotency_key="mint-001",
            db=db,
        )
        assert result["cost_cents"] == 100000
        assert result["minted_quantity"] == 1000

    @pytest.mark.asyncio
    async def test_mint_idempotent_returns_existing(self) -> None:
        """Duplicate idempotency_key returns previous result without re-executing."""
        from src.pm_clearing.domain.mint_service import execute_privileged_mint

        db = AsyncMock()
        db.execute.side_effect = self._mock_mint_db_calls(
            idempotent_exists=True,
        )

        result = await execute_privileged_mint(
            user_id=AMM_USER_ID,
            market_id="mkt-1",
            quantity=1000,
            idempotency_key="mint-001",
            db=db,
        )
        assert result.get("idempotent_hit") is True

    @pytest.mark.asyncio
    async def test_mint_insufficient_balance_raises(self) -> None:
        """Balance < cost should raise AppError code 2001."""
        from src.pm_clearing.domain.mint_service import execute_privileged_mint
        from src.pm_common.errors import AppError

        db = AsyncMock()
        db.execute.side_effect = self._mock_mint_db_calls(
            idempotent_exists=False,
            market_status="ACTIVE",
            available_balance=5000,  # only 50 dollars, need 1000 dollars
            version=1,
        )

        with pytest.raises(AppError) as exc_info:
            await execute_privileged_mint(
                user_id=AMM_USER_ID,
                market_id="mkt-1",
                quantity=1000,
                idempotency_key="mint-002",
                db=db,
            )
        assert exc_info.value.code == 2001

    @pytest.mark.asyncio
    async def test_mint_inactive_market_raises(self) -> None:
        """Non-ACTIVE market should raise AppError code 3002."""
        from src.pm_clearing.domain.mint_service import execute_privileged_mint
        from src.pm_common.errors import AppError

        db = AsyncMock()
        db.execute.side_effect = self._mock_mint_db_calls(
            idempotent_exists=False,
            market_status="SUSPENDED",
            available_balance=500000,
            version=1,
        )

        with pytest.raises(AppError) as exc_info:
            await execute_privileged_mint(
                user_id=AMM_USER_ID,
                market_id="mkt-1",
                quantity=1000,
                idempotency_key="mint-003",
                db=db,
            )
        assert exc_info.value.code == 3002

    @staticmethod
    def _mock_mint_db_calls(**kwargs):
        """Helper to create mock DB call side effects for mint tests."""
        calls = []
        if kwargs.get("idempotent_exists"):
            # First call: idempotency check returns existing record
            mock_result = MagicMock()
            mock_result.fetchone.return_value = MagicMock(
                amount=-100000, reference_id="mint-001"
            )
            calls.append(mock_result)
        else:
            # First call: idempotency check returns None
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None
            calls.append(mock_result)

            # Second call: market status check
            mock_market = MagicMock()
            mock_market.fetchone.return_value = MagicMock(
                status=kwargs.get("market_status", "ACTIVE")
            )
            calls.append(mock_market)

            # Third call: account balance check
            mock_account = MagicMock()
            mock_account.fetchone.return_value = MagicMock(
                available_balance=kwargs.get("available_balance", 0),
                version=kwargs.get("version", 0),
            )
            calls.append(mock_account)

            # Subsequent calls: UPDATE/INSERT operations return mock results
            for _ in range(10):
                mock_op = MagicMock()
                mock_op.rowcount = 1
                calls.append(mock_op)

        return calls
