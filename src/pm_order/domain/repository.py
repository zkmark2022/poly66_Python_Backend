# src/pm_order/domain/repository.py
"""OrderRepository Protocol — interface contract for persistence layer."""
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_order.domain.models import Order


class OrderRepositoryProtocol(Protocol):
    async def save(self, order: Order, db: AsyncSession) -> None: ...

    async def get_by_id(self, order_id: str, db: AsyncSession) -> Order | None: ...

    async def get_by_client_order_id(
        self, client_order_id: str, user_id: str, db: AsyncSession
    ) -> Order | None: ...

    async def update_status(self, order: Order, db: AsyncSession) -> None: ...

    async def list_by_user(
        self,
        user_id: str,
        market_id: str | None,
        statuses: list[str] | None,
        side: str | None,
        direction: str | None,
        limit: int,
        cursor_id: str | None,
        db: AsyncSession,
    ) -> list[Order]: ...
