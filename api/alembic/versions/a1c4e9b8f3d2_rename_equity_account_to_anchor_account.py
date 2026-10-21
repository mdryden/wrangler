"""rename wave_equity_account_id to wave_anchor_account_id

Revision ID: a1c4e9b8f3d2
Revises: f2a7b1c9d8e3
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c4e9b8f3d2"
down_revision: str | Sequence[str] | None = "f2a7b1c9d8e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename wave_equity_account_id to wave_anchor_account_id."""
    with op.batch_alter_table("companies", schema=None) as batch_op:
        batch_op.alter_column(
            "wave_equity_account_id",
            new_column_name="wave_anchor_account_id",
            existing_type=sa.String(),
            nullable=True,
        )


def downgrade() -> None:
    """Rename wave_anchor_account_id back to wave_equity_account_id."""
    with op.batch_alter_table("companies", schema=None) as batch_op:
        batch_op.alter_column(
            "wave_anchor_account_id",
            new_column_name="wave_equity_account_id",
            existing_type=sa.String(),
            nullable=True,
        )
