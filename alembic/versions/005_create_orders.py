"""005: create orders table

Revision ID: 005
Revises: 004
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE orders (
            id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            client_order_id     VARCHAR(64)     NOT NULL,
            market_id           VARCHAR(64)     NOT NULL,
            user_id             VARCHAR(64)     NOT NULL,
            original_side       VARCHAR(10)     NOT NULL,
            original_direction  VARCHAR(10)     NOT NULL,
            original_price      SMALLINT        NOT NULL,
            book_type           VARCHAR(20)     NOT NULL,
            book_direction      VARCHAR(10)     NOT NULL,
            book_price          SMALLINT        NOT NULL,
            price_type          VARCHAR(20)     NOT NULL DEFAULT 'LIMIT',
            time_in_force       VARCHAR(10)     NOT NULL DEFAULT 'GTC',
            quantity            INT             NOT NULL,
            filled_quantity     INT             NOT NULL DEFAULT 0,
            remaining_quantity  INT             NOT NULL,
            frozen_amount       BIGINT          NOT NULL DEFAULT 0,
            frozen_asset_type   VARCHAR(20)     NOT NULL,
            status              VARCHAR(20)     NOT NULL DEFAULT 'NEW',
            cancel_reason       VARCHAR(100),
            created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_orders_client_order_id    UNIQUE (client_order_id),
            CONSTRAINT ck_orders_original_side      CHECK (original_side IN ('YES', 'NO')),
            CONSTRAINT ck_orders_original_direction CHECK (original_direction IN ('BUY', 'SELL')),
            CONSTRAINT ck_orders_original_price     CHECK (original_price BETWEEN 1 AND 99),
            CONSTRAINT ck_orders_book_type          CHECK (
                book_type IN ('NATIVE_BUY', 'NATIVE_SELL', 'SYNTHETIC_BUY', 'SYNTHETIC_SELL')
            ),
            CONSTRAINT ck_orders_book_direction     CHECK (book_direction IN ('BUY', 'SELL')),
            CONSTRAINT ck_orders_book_price         CHECK (book_price BETWEEN 1 AND 99),
            CONSTRAINT ck_orders_price_type         CHECK (price_type IN ('LIMIT')),
            CONSTRAINT ck_orders_tif                CHECK (time_in_force IN ('GTC', 'IOC')),
            CONSTRAINT ck_orders_quantity           CHECK (quantity > 0),
            CONSTRAINT ck_orders_filled             CHECK (filled_quantity >= 0 AND filled_quantity <= quantity),
            CONSTRAINT ck_orders_remaining          CHECK (remaining_quantity >= 0 AND remaining_quantity <= quantity),
            CONSTRAINT ck_orders_fill_consistency   CHECK (filled_quantity + remaining_quantity = quantity),
            CONSTRAINT ck_orders_frozen_amount_gte_0 CHECK (frozen_amount >= 0),
            CONSTRAINT ck_orders_frozen_asset_type  CHECK (frozen_asset_type IN ('FUNDS', 'YES_SHARES', 'NO_SHARES')),
            CONSTRAINT ck_orders_book_type_dir_match CHECK (
                (book_type IN ('NATIVE_BUY', 'SYNTHETIC_BUY') AND book_direction = 'BUY') OR
                (book_type IN ('NATIVE_SELL', 'SYNTHETIC_SELL') AND book_direction = 'SELL')
            ),
            CONSTRAINT ck_orders_status             CHECK (
                status IN ('NEW', 'OPEN', 'PARTIALLY_FILLED', 'FILLED', 'CANCELLED', 'REJECTED')
            )
        );
    """)
    op.execute("CREATE INDEX idx_orders_user_status ON orders (user_id, status, created_at DESC);")
    op.execute("""
        CREATE INDEX idx_orders_market_active
        ON orders (market_id, created_at)
        WHERE status IN ('OPEN', 'PARTIALLY_FILLED');
    """)
    op.execute("""
        CREATE INDEX idx_orders_self_trade
        ON orders (market_id, user_id, book_direction)
        WHERE status IN ('OPEN', 'PARTIALLY_FILLED');
    """)
    op.execute("""
        CREATE TRIGGER trg_orders_updated_at
            BEFORE UPDATE ON orders
            FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
    """)
    op.execute("COMMENT ON TABLE orders IS '用户订单 — 单账本架构, 同时记录原始意图和订单簿视角';")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS orders CASCADE;")
