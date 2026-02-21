"""Domain models for pm_account — pure dataclasses, no SQLAlchemy dependency."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Account:
    id: str
    user_id: str
    available_balance: int   # cents
    frozen_balance: int      # cents
    version: int
    created_at: datetime
    updated_at: datetime

    @property
    def total_balance(self) -> int:
        return self.available_balance + self.frozen_balance


@dataclass
class Position:
    user_id: str
    market_id: str
    yes_volume: int = 0
    yes_cost_sum: int = 0       # cents, total purchase cost (not avg price)
    yes_pending_sell: int = 0   # frozen YES shares awaiting sell
    no_volume: int = 0
    no_cost_sum: int = 0        # cents, total purchase cost (not avg price)
    no_pending_sell: int = 0    # frozen NO shares awaiting sell
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def available_yes(self) -> int:
        return self.yes_volume - self.yes_pending_sell

    @property
    def available_no(self) -> int:
        return self.no_volume - self.no_pending_sell


@dataclass
class LedgerEntry:
    id: int                          # BIGSERIAL
    user_id: str
    entry_type: str                  # LedgerEntryType value
    amount: int                      # cents, positive=income negative=expense
    balance_after: int               # cents, available_balance snapshot after op
    reference_type: str | None = None
    reference_id: str | None = None
    description: str | None = None
    created_at: datetime | None = None
