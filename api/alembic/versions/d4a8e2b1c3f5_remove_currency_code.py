"""remove currency_code from transactions and staged_transactions

Revision ID: d4a8e2b1c3f5
Revises: e8a1f2c3b4d5
Create Date: 2026-10-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4a8e2b1c3f5"
down_revision: str | Sequence[str] | None = "e8a1f2c3b4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop currency_code from transactions and staged_transactions."""
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_column("currency_code")

    with op.batch_alter_table("staged_transactions", schema=None) as batch_op:
        batch_op.drop_column("currency_code")


def downgrade() -> None:
    """Re-add currency_code to staged_transactions and transactions with default CAD."""
    with op.batch_alter_table("staged_transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("currency_code", sa.String(), nullable=False, server_default="CAD"))

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("currency_code", sa.String(), nullable=False, server_default="CAD"))
