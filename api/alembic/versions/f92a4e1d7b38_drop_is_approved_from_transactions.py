"""drop is_approved from transactions

Revision ID: f92a4e1d7b38
Revises: 461f23e8a12c
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f92a4e1d7b38"
down_revision: str | Sequence[str] | None = "461f23e8a12c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop is_approved column from transactions table."""
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("is_approved")


def downgrade() -> None:
    """Re-add is_approved column to transactions table."""
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.text("0")))
