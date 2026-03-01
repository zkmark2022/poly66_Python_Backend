"""Verify AMM system account exists and auto_netting_enabled works.

Requires running PostgreSQL (make up && make migrate).
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.pm_account.domain.constants import AMM_USER_ID
from config.settings import settings


def _make_session() -> AsyncSession:
    """Create a fresh session with NullPool to avoid event-loop binding."""
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory()


@pytest.mark.asyncio
async def test_amm_user_exists() -> None:
    async with _make_session() as db:
        result = await db.execute(
            text("SELECT id, username FROM users WHERE id = :uid"),
            {"uid": AMM_USER_ID},
        )
        row = result.fetchone()
    assert row is not None
    assert row.username == "amm_market_maker"


@pytest.mark.asyncio
async def test_amm_account_netting_disabled() -> None:
    async with _make_session() as db:
        result = await db.execute(
            text("SELECT auto_netting_enabled FROM accounts WHERE user_id = :uid"),
            {"uid": AMM_USER_ID},
        )
        row = result.fetchone()
    assert row is not None
    assert row.auto_netting_enabled is False


@pytest.mark.asyncio
async def test_normal_account_netting_enabled_by_default() -> None:
    """Verify all non-AMM accounts default to auto_netting_enabled = true."""
    async with _make_session() as db:
        result = await db.execute(
            text(
                "SELECT COUNT(*) FROM accounts "
                "WHERE user_id != :uid AND auto_netting_enabled = false"
            ),
            {"uid": AMM_USER_ID},
        )
        count = result.scalar()
    assert count == 0
