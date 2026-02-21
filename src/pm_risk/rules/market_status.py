from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.errors import MarketNotActiveError, MarketNotFoundError

_SQL = text("SELECT status FROM markets WHERE id = :market_id")


async def check_market_active(market_id: str, db: AsyncSession) -> None:
    result = await db.execute(_SQL, {"market_id": market_id})
    status = result.scalar_one_or_none()
    if status is None:
        raise MarketNotFoundError(market_id)
    if status != "ACTIVE":
        raise MarketNotActiveError(market_id)
