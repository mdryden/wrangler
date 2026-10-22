"""add url to transactions

Revision ID: d5c8e3f1a2b7
Revises: c7b9e2d1f4a6
Create Date: 2026-10-22

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5c8e3f1a2b7"
down_revision: str | Sequence[str] | None = "c7b9e2d1f4a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add url column to transactions."""
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("url", sa.String(), nullable=True))


def downgrade() -> None:
    """Drop url column from transactions."""
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("url")
