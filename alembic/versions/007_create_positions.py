"""007: create positions table

Revision ID: 007
Revises: 006
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE positions (
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             VARCHAR(64) NOT NULL,
            market_id           VARCHAR(64) NOT NULL,
            yes_volume          INT         NOT NULL DEFAULT 0,
            yes_cost_sum        BIGINT      NOT NULL DEFAULT 0,
            yes_pending_sell    INT         NOT NULL DEFAULT 0,
            no_volume           INT         NOT NULL DEFAULT 0,
            no_cost_sum         BIGINT      NOT NULL DEFAULT 0,
            no_pending_sell     INT         NOT NULL DEFAULT 0,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_positions_user_market         UNIQUE (user_id, market_id),
            CONSTRAINT ck_positions_yes_volume_gte_0    CHECK (yes_volume >= 0),
            CONSTRAINT ck_positions_yes_cost_gte_0      CHECK (yes_cost_sum >= 0),
            CONSTRAINT ck_positions_yes_pending_gte_0   CHECK (yes_pending_sell >= 0),
            CONSTRAINT ck_positions_yes_pending_lte_vol CHECK (yes_pending_sell <= yes_volume),
            CONSTRAINT ck_positions_no_volume_gte_0     CHECK (no_volume >= 0),
            CONSTRAINT ck_positions_no_cost_gte_0       CHECK (no_cost_sum >= 0),
            CONSTRAINT ck_positions_no_pending_gte_0    CHECK (no_pending_sell >= 0),
            CONSTRAINT ck_positions_no_pending_lte_vol  CHECK (no_pending_sell <= no_volume)
        );
    """)
    op.execute("CREATE INDEX idx_positions_user ON positions (user_id);")
    op.execute("""
        CREATE TRIGGER trg_positions_updated_at
            BEFORE UPDATE ON positions
            FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
    """)
    op.execute("COMMENT ON TABLE positions IS '用户持仓 — 单账本架构, 每用户每话题一行, YES/NO 合并';")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS positions CASCADE;")
