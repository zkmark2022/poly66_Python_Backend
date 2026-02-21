"""008: create ledger_entries table

Revision ID: 008
Revises: 007
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE ledger_entries (
            id              BIGSERIAL       PRIMARY KEY,
            user_id         VARCHAR(64)     NOT NULL,
            entry_type      VARCHAR(30)     NOT NULL,
            amount          BIGINT          NOT NULL,
            balance_after   BIGINT          NOT NULL,
            reference_type  VARCHAR(30),
            reference_id    VARCHAR(64),
            description     VARCHAR(500),
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_ledger_entry_type CHECK (
                entry_type IN (
                    'DEPOSIT', 'WITHDRAW',
                    'ORDER_FREEZE', 'ORDER_UNFREEZE',
                    'MINT_COST', 'MINT_RESERVE_IN',
                    'BURN_REVENUE', 'BURN_RESERVE_OUT',
                    'TRANSFER_PAYMENT', 'TRANSFER_RECEIPT',
                    'NETTING', 'NETTING_RESERVE_OUT',
                    'FEE', 'FEE_REVENUE',
                    'SETTLEMENT_PAYOUT', 'SETTLEMENT_VOID'
                )
            ),
            CONSTRAINT ck_ledger_balance_gte_0 CHECK (balance_after >= 0)
        );
    """)
    op.execute("CREATE INDEX idx_ledger_user_time ON ledger_entries (user_id, created_at DESC);")
    op.execute("""
        CREATE INDEX idx_ledger_reference
        ON ledger_entries (reference_type, reference_id)
        WHERE reference_id IS NOT NULL;
    """)
    op.execute("CREATE INDEX idx_ledger_type ON ledger_entries (entry_type, created_at);")
    op.execute("COMMENT ON TABLE ledger_entries IS '资金流水 — Append-Only, 永不修改/删除, 所有金额单位: 美分';")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ledger_entries CASCADE;")
