"""010: alter orders.id from UUID to VARCHAR(64)

The application uses snowflake-style string IDs (generate_id()), not UUIDs.
The original UUID column type causes "invalid input syntax for type uuid" on
every INSERT because snowflake IDs are numeric strings, not UUID-format strings.

Revision ID: 010
Revises: 009
Create Date: 2026-02-21
"""
from typing import Sequence, Union
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE orders ALTER COLUMN id TYPE VARCHAR(64) USING id::TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE orders ALTER COLUMN id TYPE UUID USING id::UUID;")
