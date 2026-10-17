"""replace sync_status with is_locked on allocations

Revision ID: a3c8d9e21f04
Revises: f92a4e1d7b38
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c8d9e21f04"
down_revision: str | Sequence[str] | None = "f92a4e1d7b38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add is_locked column, migrate SYNCED rows to True, and drop sync_status on allocations."""
    with op.batch_alter_table("allocations") as batch_op:
        batch_op.add_column(sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    op.execute(sa.text("UPDATE allocations SET is_locked = 1 WHERE sync_status = 'SYNCED'"))

    with op.batch_alter_table("allocations") as batch_op:
        batch_op.drop_column("sync_status")


def downgrade() -> None:
    """Re-add sync_status column, migrate is_locked rows to SYNCED, and drop is_locked on allocations."""
    with op.batch_alter_table("allocations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "sync_status",
                sa.Enum("PENDING", "SYNCED", name="sync_status", native_enum=False),
                nullable=False,
                server_default="PENDING",
            )
        )

    op.execute(sa.text("UPDATE allocations SET sync_status = 'SYNCED' WHERE is_locked = 1"))

    with op.batch_alter_table("allocations") as batch_op:
        batch_op.drop_column("is_locked")
