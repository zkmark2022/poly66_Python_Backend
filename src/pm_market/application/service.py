"""MarketApplicationService — thin composition layer.

All methods are read-only; no commit/rollback needed.
The caller (router) passes db session; service delegates to repository.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.errors import MarketNotActiveError, MarketNotFoundError
from src.pm_market.application.schemas import (
    MarketDetail,
    MarketListItem,
    MarketListResponse,
    OrderbookResponse,
    cursor_decode,
    cursor_encode,
)
from src.pm_market.domain.repository import MarketRepositoryProtocol
from src.pm_market.infrastructure.persistence import MarketRepository


class MarketApplicationService:
    def __init__(self, repo: MarketRepositoryProtocol | None = None) -> None:
        self._repo: MarketRepositoryProtocol = repo or MarketRepository()

    async def list_markets(
        self,
        db: AsyncSession,
        status: str | None,
        category: str | None,
        cursor: str | None,
        limit: int,
    ) -> MarketListResponse:
        # status=None → default ACTIVE; status='ALL' → no filter
        sql_status = None if status == "ALL" else (status or "ACTIVE")
        cursor_ts, cursor_id = cursor_decode(cursor)

        # Fetch limit+1 to detect has_more without COUNT(*)
        markets = await self._repo.list_markets(
            db, sql_status, category, cursor_ts, cursor_id, limit + 1
        )
        has_more = len(markets) > limit
        page = markets[:limit]

        items = [MarketListItem.from_domain(m) for m in page]
        next_cursor = cursor_encode(page[-1]) if has_more and page else None
        return MarketListResponse(items=items, next_cursor=next_cursor, has_more=has_more)

    async def get_market(self, db: AsyncSession, market_id: str) -> MarketDetail:
        market = await self._repo.get_market_by_id(db, market_id)
        if market is None:
            raise MarketNotFoundError(market_id)
        return MarketDetail.from_domain(market)

    async def get_orderbook(
        self, db: AsyncSession, market_id: str, levels: int
    ) -> OrderbookResponse:
        market = await self._repo.get_market_by_id(db, market_id)
        if market is None:
            raise MarketNotFoundError(market_id)
        if market.status != "ACTIVE":
            raise MarketNotActiveError(market_id)
        snapshot = await self._repo.get_orderbook_snapshot(db, market_id, levels)
        return OrderbookResponse.from_snapshot(snapshot)
