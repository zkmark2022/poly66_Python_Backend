"""004: create markets table

Revision ID: 004
Revises: 003
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE markets (
            id                      VARCHAR(64)     PRIMARY KEY,
            title                   VARCHAR(500)    NOT NULL,
            description             TEXT,
            category                VARCHAR(64),
            status                  VARCHAR(20)     NOT NULL DEFAULT 'DRAFT',
            min_price_cents         SMALLINT        NOT NULL DEFAULT 1,
            max_price_cents         SMALLINT        NOT NULL DEFAULT 99,
            max_order_quantity      INT             NOT NULL DEFAULT 10000,
            max_position_per_user   INT             NOT NULL DEFAULT 25000,
            max_order_amount_cents  BIGINT          NOT NULL DEFAULT 1000000,
            maker_fee_bps           SMALLINT        NOT NULL DEFAULT 10,
            taker_fee_bps           SMALLINT        NOT NULL DEFAULT 20,
            trading_start_at        TIMESTAMPTZ,
            trading_end_at          TIMESTAMPTZ,
            resolution_date         TIMESTAMPTZ,
            resolved_at             TIMESTAMPTZ,
            settled_at              TIMESTAMPTZ,
            resolution_result       VARCHAR(10),
            reserve_balance         BIGINT          NOT NULL DEFAULT 0,
            pnl_pool                BIGINT          NOT NULL DEFAULT 0,
            total_yes_shares        BIGINT          NOT NULL DEFAULT 0,
            total_no_shares         BIGINT          NOT NULL DEFAULT 0,
            created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_markets_reserve_gte_0          CHECK (reserve_balance >= 0),
            CONSTRAINT ck_markets_yes_shares_gte_0       CHECK (total_yes_shares >= 0),
            CONSTRAINT ck_markets_no_shares_gte_0        CHECK (total_no_shares >= 0),
            CONSTRAINT ck_markets_shares_balanced        CHECK (total_yes_shares = total_no_shares),
            CONSTRAINT ck_markets_reserve_consistency    CHECK (reserve_balance = total_yes_shares * 100),
            CONSTRAINT ck_markets_status CHECK (
                status IN ('DRAFT', 'ACTIVE', 'SUSPENDED', 'HALTED', 'RESOLVED', 'SETTLED', 'VOIDED')
            ),
            CONSTRAINT ck_markets_price_range CHECK (
                min_price_cents >= 1 AND max_price_cents <= 99
                AND min_price_cents < max_price_cents
            ),
            CONSTRAINT ck_markets_fee CHECK (
                maker_fee_bps >= 0 AND maker_fee_bps <= 1000
                AND taker_fee_bps >= 0 AND taker_fee_bps <= 1000
            ),
            CONSTRAINT ck_markets_resolution CHECK (
                resolution_result IS NULL OR resolution_result IN ('YES', 'NO', 'VOID')
            )
        );
    """)
    op.execute("CREATE INDEX idx_markets_status ON markets (status);")
    op.execute("""
        CREATE TRIGGER trg_markets_updated_at
            BEFORE UPDATE ON markets
            FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
    """)
    op.execute("COMMENT ON TABLE markets IS '预测话题 — 交易规则/风控参数/单账本托管状态/裁决结果';")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS markets CASCADE;")
