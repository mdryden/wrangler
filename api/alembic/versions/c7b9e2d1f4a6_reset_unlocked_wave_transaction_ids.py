"""reset wave_transaction_id on unlocked allocations

Revision ID: c7b9e2d1f4a6
Revises: a1c4e9b8f3d2
Create Date: 2026-10-21

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7b9e2d1f4a6"
down_revision: str | Sequence[str] | None = "a1c4e9b8f3d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reset lingering wave_transaction_id on unlocked allocations."""
    op.execute("UPDATE allocations SET wave_transaction_id = NULL WHERE is_locked = 0 AND wave_transaction_id IS NOT NULL")


def downgrade() -> None:
    """Data cleanup is irreversible; no-op on downgrade."""
    pass
