"""014: add AMM prerequisites — auto_netting_enabled column + AMM system account

Revision ID: 014
Revises: 013
Create Date: 2026-02-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add auto_netting_enabled column (default TRUE for all existing accounts)
    op.add_column(
        "accounts",
        sa.Column(
            "auto_netting_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # 2. Insert AMM system user
    op.execute(
        """
        INSERT INTO users (id, username, email, password_hash, is_active, created_at, updated_at)
        VALUES (
            '00000000-0000-4000-a000-000000000001',
            'amm_market_maker',
            'amm@system.internal',
            '$2b$12$AMM.SYSTEM.ACCOUNT.NO.LOGIN.PLACEHOLDER.HASH',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO NOTHING;
        """
    )

    # 3. Insert AMM system account with auto_netting disabled
    op.execute(
        """
        INSERT INTO accounts (user_id, available_balance, frozen_balance, version, auto_netting_enabled)
        VALUES (
            '00000000-0000-4000-a000-000000000001',
            0,
            0,
            0,
            false
        )
        ON CONFLICT (user_id) DO UPDATE SET auto_netting_enabled = false;
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM accounts WHERE user_id = '00000000-0000-4000-a000-000000000001'"
    )
    op.execute(
        "DELETE FROM users WHERE id = '00000000-0000-4000-a000-000000000001'"
    )
    op.drop_column("accounts", "auto_netting_enabled")
