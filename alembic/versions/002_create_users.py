"""002: create users table

Revision ID: 002
Revises: 001
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
            id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            username        VARCHAR(64)     NOT NULL,
            email           VARCHAR(255)    NOT NULL,
            password_hash   VARCHAR(255)    NOT NULL,
            is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_users_username    UNIQUE (username),
            CONSTRAINT uq_users_email       UNIQUE (email),
            CONSTRAINT ck_users_username_len CHECK (LENGTH(username) >= 3)
        );
    """)
    op.execute("CREATE INDEX idx_users_email ON users (email);")
    op.execute("""
        CREATE TRIGGER trg_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION fn_update_timestamp();
    """)
    op.execute("COMMENT ON TABLE users IS '用户表 — 注册/登录认证';")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users CASCADE;")
