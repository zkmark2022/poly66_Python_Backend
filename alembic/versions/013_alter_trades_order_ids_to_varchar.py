"""013: alter trades order ID columns from UUID to VARCHAR(64)

orders.id was changed to VARCHAR(64) in migration 012.
Trades columns referencing order IDs must match.

Revision ID: 013
Revises: 012
Create Date: 2026-02-21
"""
from typing import Sequence, Union
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in ("buy_order_id", "sell_order_id", "maker_order_id", "taker_order_id"):
        op.execute(f"ALTER TABLE trades ALTER COLUMN {col} TYPE VARCHAR(64) USING {col}::TEXT;")


def downgrade() -> None:
    for col in ("buy_order_id", "sell_order_id", "maker_order_id", "taker_order_id"):
        op.execute(f"ALTER TABLE trades ALTER COLUMN {col} TYPE UUID USING {col}::UUID;")
