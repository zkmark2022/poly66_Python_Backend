"""SQLAlchemy ORM model for the markets table.

Used for type reference only — persistence.py uses raw text() SQL.
Alembic migrations (004_create_markets.py) are the authoritative DDL source.
"""

from datetime import datetime

from sqlalchemy import BigInteger, SmallInteger, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MarketORM(Base):
    __tablename__ = "markets"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    min_price_cents: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_price_cents: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_order_quantity: Mapped[int] = mapped_column(nullable=False)
    max_position_per_user: Mapped[int] = mapped_column(nullable=False)
    max_order_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    maker_fee_bps: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    taker_fee_bps: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    trading_start_at: Mapped[datetime | None] = mapped_column()
    trading_end_at: Mapped[datetime | None] = mapped_column()
    resolution_date: Mapped[datetime | None] = mapped_column()
    resolved_at: Mapped[datetime | None] = mapped_column()
    settled_at: Mapped[datetime | None] = mapped_column()
    resolution_result: Mapped[str | None] = mapped_column(Text)
    reserve_balance: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pnl_pool: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_yes_shares: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_no_shares: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
