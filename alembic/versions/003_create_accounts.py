"""003: create accounts table

Revision ID: 003
Revises: 002
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE accounts (
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             VARCHAR(64) NOT NULL,
            available_balance   BIGINT      NOT NULL DEFAULT 0,
            frozen_balance      BIGINT      NOT NULL DEFAULT 0,
            version             BIGINT      NOT NULL DEFAULT 0,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_accounts_user_id          UNIQUE (user_id),
            CONSTRAINT ck_accounts_available_gte_0  CHECK (available_balance >= 0),
            CONSTRAINT ck_accounts_frozen_gte_0     CHECK (frozen_balance >= 0)
        );
    """)
    op.execute("""
        CREATE TRIGGER trg_accounts_updated_at
            BEFORE UPDATE ON accounts
            FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
    """)
    op.execute("COMMENT ON TABLE accounts IS '用户资金账户 — 所有金额单位: 美分 (cents)';")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS accounts CASCADE;")
