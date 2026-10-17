"""add staging tables

Revision ID: c4e9b2a17d05
Revises: a3c8d9e21f04
Create Date: 2026-10-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e9b2a17d05"
down_revision: str | Sequence[str] | None = "a3c8d9e21f04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create staged_transactions and staged_allocations tables."""
    op.create_table(
        "staged_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency_code", sa.String(), nullable=False),
        sa.Column("receipt_file_path", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("is_marked_imported", sa.Boolean(), nullable=False),
        sa.Column("ledger_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ledger_transaction_id"], ["transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_staged_transactions_source_external_id"),
    )
    op.create_index("ix_staged_transactions_source", "staged_transactions", ["source"], unique=False)
    op.create_index("ix_staged_transactions_status", "staged_transactions", ["status"], unique=False)

    op.create_table(
        "staged_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("staged_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("is_personal", sa.Boolean(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["staged_transaction_id"], ["staged_transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop staged_allocations and staged_transactions tables."""
    op.drop_table("staged_allocations")
    op.drop_index("ix_staged_transactions_status", table_name="staged_transactions")
    op.drop_index("ix_staged_transactions_source", table_name="staged_transactions")
    op.drop_table("staged_transactions")
