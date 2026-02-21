"""009: create wal_events table

Revision ID: 009
Revises: 008
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE wal_events (
            id              BIGSERIAL       PRIMARY KEY,
            market_id       VARCHAR(64)     NOT NULL,
            event_type      VARCHAR(30)     NOT NULL,
            payload         JSONB           NOT NULL,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_wal_event_type CHECK (
                event_type IN (
                    'ORDER_ACCEPTED',
                    'ORDER_MATCHED',
                    'ORDER_PARTIALLY_FILLED',
                    'ORDER_CANCELLED',
                    'ORDER_EXPIRED'
                )
            )
        );
    """)
    op.execute("CREATE INDEX idx_wal_market_time ON wal_events (market_id, created_at);")
    op.execute("CREATE INDEX idx_wal_order_id ON wal_events USING GIN ((payload->'order_id'));")
    op.execute("COMMENT ON TABLE wal_events IS '订单簿变更审计日志 — Append-Only, 仅用于事后排查和分析';")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS wal_events CASCADE;")
