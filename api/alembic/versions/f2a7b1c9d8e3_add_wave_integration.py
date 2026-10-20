"""add wave integration tables and columns

Revision ID: f2a7b1c9d8e3
Revises: d4a8e2b1c3f5
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a7b1c9d8e3"
down_revision: str | Sequence[str] | None = "d4a8e2b1c3f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add Wave integration columns and wave_categories table."""
    with op.batch_alter_table("companies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("wave_api_token", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("wave_business_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("wave_business_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("wave_equity_account_id", sa.String(), nullable=True))

    op.create_table(
        "wave_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("wave_account_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("account_type", sa.String(), nullable=False),
        sa.Column("account_subtype", sa.String(), nullable=True),
        sa.Column("is_uncategorized", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "wave_account_id", name="uq_wave_categories_company_account"),
    )

    with op.batch_alter_table("allocations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("wave_category_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("wave_transaction_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_allocations_wave_category_id",
            "wave_categories",
            ["wave_category_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Remove Wave integration columns and wave_categories table."""
    with op.batch_alter_table("allocations", schema=None) as batch_op:
        batch_op.drop_constraint("fk_allocations_wave_category_id", type_="foreignkey")
        batch_op.drop_column("wave_transaction_id")
        batch_op.drop_column("wave_category_id")

    op.drop_table("wave_categories")

    with op.batch_alter_table("companies", schema=None) as batch_op:
        batch_op.drop_column("wave_equity_account_id")
        batch_op.drop_column("wave_business_name")
        batch_op.drop_column("wave_business_id")
        batch_op.drop_column("wave_api_token")
