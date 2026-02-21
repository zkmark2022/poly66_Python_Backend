"""011: seed initial data

Revision ID: 011
Revises: 010
Create Date: 2026-02-20
"""

from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # System special accounts
    op.execute("""
        INSERT INTO accounts (user_id, available_balance, frozen_balance, version)
        VALUES ('SYSTEM_RESERVE', 0, 0, 0);
    """)
    op.execute("""
        INSERT INTO accounts (user_id, available_balance, frozen_balance, version)
        VALUES ('PLATFORM_FEE', 0, 0, 0);
    """)

    # Sample markets
    op.execute("""
        INSERT INTO markets (
            id, title, description, category, status,
            min_price_cents, max_price_cents,
            max_order_quantity, max_position_per_user, max_order_amount_cents,
            maker_fee_bps, taker_fee_bps,
            trading_start_at, resolution_date
        ) VALUES
            ('MKT-BTC-100K-2026',
             'Will BTC exceed $100,000 by end of 2026?',
             'Resolves YES if Bitcoin price exceeds $100,000 on any major exchange before 2027-01-01 00:00 UTC.',
             'crypto', 'ACTIVE',
             1, 99, 10000, 25000, 1000000, 10, 20,
             '2026-01-01T00:00:00Z', '2026-12-31T23:59:59Z'),
            ('MKT-ETH-10K-2026',
             'Will ETH exceed $10,000 by end of 2026?',
             'Resolves YES if Ethereum price exceeds $10,000 on any major exchange before 2027-01-01 00:00 UTC.',
             'crypto', 'ACTIVE',
             1, 99, 10000, 25000, 1000000, 10, 20,
             '2026-01-01T00:00:00Z', '2026-12-31T23:59:59Z'),
            ('MKT-FED-RATE-CUT-2026Q2',
             'Will the Fed cut rates in Q2 2026?',
             'Resolves YES if the Federal Reserve announces a rate cut at any FOMC meeting in April, May, or June 2026.',
             'economics', 'ACTIVE',
             1, 99, 10000, 25000, 1000000, 10, 20,
             '2026-01-01T00:00:00Z', '2026-06-30T23:59:59Z');
    """)


def downgrade() -> None:
    op.execute("DELETE FROM markets WHERE id IN ('MKT-BTC-100K-2026', 'MKT-ETH-10K-2026', 'MKT-FED-RATE-CUT-2026Q2');")
    op.execute("DELETE FROM accounts WHERE user_id IN ('SYSTEM_RESERVE', 'PLATFORM_FEE');")
