"""006: create trades table

Revision ID: 006
Revises: 005
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE trades (
            id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            trade_id        VARCHAR(64)     NOT NULL,
            market_id       VARCHAR(64)     NOT NULL,
            scenario        VARCHAR(20)     NOT NULL,
            buy_order_id    UUID            NOT NULL,
            sell_order_id   UUID            NOT NULL,
            buy_user_id     VARCHAR(64)     NOT NULL,
            sell_user_id    VARCHAR(64)     NOT NULL,
            buy_book_type   VARCHAR(20)     NOT NULL,
            sell_book_type  VARCHAR(20)     NOT NULL,
            price           SMALLINT        NOT NULL,
            quantity        INT             NOT NULL,
            maker_order_id  UUID            NOT NULL,
            taker_order_id  UUID            NOT NULL,
            maker_fee       BIGINT          NOT NULL DEFAULT 0,
            taker_fee       BIGINT          NOT NULL DEFAULT 0,
            buy_realized_pnl  BIGINT        DEFAULT NULL,
            sell_realized_pnl BIGINT        DEFAULT NULL,
            executed_at     TIMESTAMPTZ     NOT NULL,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_trades_trade_id       UNIQUE (trade_id),
            CONSTRAINT ck_trades_scenario       CHECK (
                scenario IN ('MINT', 'TRANSFER_YES', 'TRANSFER_NO', 'BURN')
            ),
            CONSTRAINT ck_trades_buy_book_type  CHECK (
                buy_book_type IN ('NATIVE_BUY', 'SYNTHETIC_BUY')
            ),
            CONSTRAINT ck_trades_sell_book_type CHECK (
                sell_book_type IN ('NATIVE_SELL', 'SYNTHETIC_SELL')
            ),
            CONSTRAINT ck_trades_price          CHECK (price BETWEEN 1 AND 99),
            CONSTRAINT ck_trades_quantity       CHECK (quantity > 0),
            CONSTRAINT ck_trades_fee_gte_0      CHECK (maker_fee >= 0 AND taker_fee >= 0),
            CONSTRAINT ck_trades_diff_users     CHECK (buy_user_id != sell_user_id)
        );
    """)
    op.execute("CREATE INDEX idx_trades_buy_user ON trades (buy_user_id, executed_at DESC);")
    op.execute("CREATE INDEX idx_trades_sell_user ON trades (sell_user_id, executed_at DESC);")
    op.execute("CREATE INDEX idx_trades_market_time ON trades (market_id, executed_at DESC);")
    op.execute("CREATE INDEX idx_trades_scenario ON trades (market_id, scenario);")
    op.execute("COMMENT ON TABLE trades IS '撮合成交记录 — 单账本架构, 含撮合场景';")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS trades CASCADE;")
