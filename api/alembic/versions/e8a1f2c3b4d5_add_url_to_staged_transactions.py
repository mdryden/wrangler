"""add url to staged_transactions

Revision ID: e8a1f2c3b4d5
Revises: b7d3e5f29a10
Create Date: 2026-10-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8a1f2c3b4d5"
down_revision: str | Sequence[str] | None = "b7d3e5f29a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add url column to staged_transactions."""
    with op.batch_alter_table("staged_transactions") as batch_op:
        batch_op.add_column(sa.Column("url", sa.String(), nullable=True))


def downgrade() -> None:
    """Drop url column from staged_transactions."""
    with op.batch_alter_table("staged_transactions") as batch_op:
        batch_op.drop_column("url")
