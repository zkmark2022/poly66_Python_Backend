# src/pm_account/application/positions_schemas.py
"""Pydantic schemas for positions API."""
from pydantic import BaseModel


class PositionResponse(BaseModel):
    market_id: str
    yes_volume: int
    yes_cost_sum: int
    no_volume: int
    no_cost_sum: int


class PositionListResponse(BaseModel):
    items: list[PositionResponse]
    total: int
