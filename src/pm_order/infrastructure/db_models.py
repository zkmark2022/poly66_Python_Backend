# src/pm_order/infrastructure/db_models.py
"""SQLAlchemy ORM model for the orders table (DDL reference only — queries use raw SQL)."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.pm_common.database import Base


class OrderORM(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    market_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    original_side: Mapped[str] = mapped_column(String(10), nullable=False)
    original_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    original_price: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    book_type: Mapped[str] = mapped_column(String(20), nullable=False)
    book_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    book_price: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    price_type: Mapped[str] = mapped_column(String(10), nullable=False, default="LIMIT")
    time_in_force: Mapped[str] = mapped_column(String(3), nullable=False, default="GTC")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remaining_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    frozen_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    frozen_asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    cancel_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
