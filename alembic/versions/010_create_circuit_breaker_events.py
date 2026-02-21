"""010: create circuit_breaker_events table

Revision ID: 010
Revises: 009
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE circuit_breaker_events (
            id              BIGSERIAL       PRIMARY KEY,
            market_id       VARCHAR(64)     NOT NULL,
            trigger_reason  VARCHAR(50)     NOT NULL,
            context         JSONB           NOT NULL DEFAULT '{}',
            resolved_at     TIMESTAMPTZ,
            resolved_by     VARCHAR(50),
            resolution_note TEXT,
            triggered_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX idx_cb_market ON circuit_breaker_events (market_id, triggered_at DESC);")
    op.execute("COMMENT ON TABLE circuit_breaker_events IS '熔断事件记录 — 含触发原因和人工解除信息';")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS circuit_breaker_events CASCADE;")
