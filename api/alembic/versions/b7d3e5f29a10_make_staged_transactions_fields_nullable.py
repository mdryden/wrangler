"""make staged_transactions date description total_amount nullable

Revision ID: b7d3e5f29a10
Revises: c4e9b2a17d05
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d3e5f29a10"
down_revision: str | Sequence[str] | None = "c4e9b2a17d05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Alter staged_transactions to make date, description, and total_amount nullable."""
    with op.batch_alter_table("staged_transactions") as batch_op:
        batch_op.alter_column("date", existing_type=sa.Date(), nullable=True)
        batch_op.alter_column("description", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("total_amount", existing_type=sa.Numeric(precision=12, scale=2), nullable=True)


def downgrade() -> None:
    """Revert staged_transactions date, description, and total_amount to not nullable."""
    with op.batch_alter_table("staged_transactions") as batch_op:
        batch_op.alter_column("total_amount", existing_type=sa.Numeric(precision=12, scale=2), nullable=False)
        batch_op.alter_column("description", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("date", existing_type=sa.Date(), nullable=False)
