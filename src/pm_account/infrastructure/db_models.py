"""SQLAlchemy ORM models for pm_account.

These map to existing tables created by Alembic migrations.
DO NOT add/remove columns here without a corresponding migration.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pm_common.database import Base


class AccountORM(Base):
    __tablename__ = "accounts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    available_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    frozen_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PositionORM(Base):
    __tablename__ = "positions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    market_id: Mapped[str] = mapped_column(String(64), nullable=False)
    yes_volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    yes_cost_sum: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    yes_pending_sell: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    no_volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    no_cost_sum: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    no_pending_sell: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LedgerEntryORM(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # NOTE: No updated_at — ledger_entries is append-only
