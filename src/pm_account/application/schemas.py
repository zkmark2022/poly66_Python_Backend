"""Pydantic schemas and cursor utilities for pm_account API."""

import base64
import json

from pydantic import BaseModel, Field

from src.pm_common.cents import cents_to_display

# ---------------------------------------------------------------------------
# Cursor-based pagination utilities
# ---------------------------------------------------------------------------


def cursor_encode(last_id: int) -> str:
    """Encode a BIGINT primary key into an opaque Base64 cursor string."""
    payload = json.dumps({"id": last_id})
    return base64.b64encode(payload.encode()).decode()


def cursor_decode(cursor: str | None) -> int | None:
    """Decode a cursor string back to the last seen id. Returns None on error."""
    if cursor is None:
        return None
    try:
        payload = json.loads(base64.b64decode(cursor.encode()).decode())
        return int(payload["id"])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class DepositRequest(BaseModel):
    amount_cents: int = Field(..., gt=0, description="Amount to deposit in cents")


class WithdrawRequest(BaseModel):
    amount_cents: int = Field(..., gt=0, description="Amount to withdraw in cents")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class BalanceResponse(BaseModel):
    user_id: str
    available_balance_cents: int
    available_balance_display: str
    frozen_balance_cents: int
    frozen_balance_display: str
    total_balance_cents: int
    total_balance_display: str

    @classmethod
    def from_cents(
        cls,
        user_id: str,
        available: int,
        frozen: int,
    ) -> "BalanceResponse":
        return cls(
            user_id=user_id,
            available_balance_cents=available,
            available_balance_display=cents_to_display(available),
            frozen_balance_cents=frozen,
            frozen_balance_display=cents_to_display(frozen),
            total_balance_cents=available + frozen,
            total_balance_display=cents_to_display(available + frozen),
        )


class DepositResponse(BaseModel):
    available_balance_cents: int
    available_balance_display: str
    deposited_cents: int
    deposited_display: str
    ledger_entry_id: int

    @classmethod
    def from_result(cls, available: int, amount: int, entry_id: int) -> "DepositResponse":
        return cls(
            available_balance_cents=available,
            available_balance_display=cents_to_display(available),
            deposited_cents=amount,
            deposited_display=cents_to_display(amount),
            ledger_entry_id=entry_id,
        )


class WithdrawResponse(BaseModel):
    available_balance_cents: int
    available_balance_display: str
    withdrawn_cents: int
    withdrawn_display: str
    ledger_entry_id: int

    @classmethod
    def from_result(cls, available: int, amount: int, entry_id: int) -> "WithdrawResponse":
        return cls(
            available_balance_cents=available,
            available_balance_display=cents_to_display(available),
            withdrawn_cents=amount,
            withdrawn_display=cents_to_display(amount),
            ledger_entry_id=entry_id,
        )


class LedgerEntryItem(BaseModel):
    id: int
    entry_type: str
    amount_cents: int
    amount_display: str
    balance_after_cents: int
    balance_after_display: str
    reference_type: str | None
    reference_id: str | None
    description: str | None
    created_at: str  # ISO8601 string


class LedgerResponse(BaseModel):
    items: list[LedgerEntryItem]
    next_cursor: str | None
    has_more: bool
