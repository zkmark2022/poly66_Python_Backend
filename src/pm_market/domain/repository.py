# src/pm_market/domain/repository.py
"""Repository Protocol — dependency inversion for testability.

Unit tests inject a mock that conforms to this Protocol.
Infrastructure layer provides the real implementation.
"""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_market.domain.models import Market, OrderbookSnapshot


class MarketRepositoryProtocol(Protocol):
    async def list_markets(
        self,
        db: AsyncSession,
        status: str | None,
        category: str | None,
        cursor_ts: str | None,
        cursor_id: str | None,
        limit: int,
    ) -> list[Market]: ...

    async def get_market_by_id(
        self,
        db: AsyncSession,
        market_id: str,
    ) -> Market | None: ...

    async def get_orderbook_snapshot(
        self,
        db: AsyncSession,
        market_id: str,
        levels: int,
    ) -> OrderbookSnapshot: ...
