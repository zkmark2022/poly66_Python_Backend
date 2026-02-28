"""AMM-specific request/response schemas for Mint and Burn APIs."""
from pydantic import BaseModel, Field


class MintRequest(BaseModel):
    market_id: str
    quantity: int = Field(gt=0, description="Number of YES+NO share pairs to mint")
    idempotency_key: str = Field(
        min_length=1, max_length=128, description="Unique key to prevent duplicate mints"
    )


class MintResponse(BaseModel):
    market_id: str
    minted_quantity: int
    cost_cents: int
    new_yes_inventory: int
    new_no_inventory: int
    remaining_balance_cents: int


class BurnRequest(BaseModel):
    market_id: str
    quantity: int = Field(gt=0, description="Number of YES+NO share pairs to burn")
    idempotency_key: str = Field(
        min_length=1, max_length=128, description="Unique key to prevent duplicate burns"
    )


class BurnResponse(BaseModel):
    market_id: str
    burned_quantity: int
    recovered_cents: int
    new_yes_inventory: int
    new_no_inventory: int
    remaining_balance_cents: int
