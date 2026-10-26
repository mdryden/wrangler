"""add monthly checklist tables

Revision ID: e1f2a3b4c5d6
Revises: d5c8e3f1a2b7
Create Date: 2026-10-26

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d5c8e3f1a2b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create checklist_configs and monthly_checklists tables."""
    op.create_table(
        "checklist_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("chequing_wave_account_id", sa.String(), nullable=True),
        sa.Column("chequing_wave_account_name", sa.String(), nullable=True),
        sa.Column("mastercard_wave_account_id", sa.String(), nullable=True),
        sa.Column("mastercard_wave_account_name", sa.String(), nullable=True),
        sa.Column("tax_expense_wave_account_id", sa.String(), nullable=True),
        sa.Column("tax_expense_wave_account_name", sa.String(), nullable=True),
        sa.Column("tax_payable_wave_account_id", sa.String(), nullable=True),
        sa.Column("tax_payable_wave_account_name", sa.String(), nullable=True),
        sa.Column("wave_web_business_slug", sa.String(), nullable=False, server_default="d2977f10-6793-4504-a139-f0d6872b2628"),
        sa.Column("last_chequing_tx_date", sa.Date(), nullable=True),
        sa.Column("last_mastercard_tx_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "monthly_checklists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("year_month", sa.String(length=7), nullable=False),
        sa.Column("completed_steps_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("net_operating_cash", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False, server_default="12.00"),
        sa.Column("tax_accrual_wave_tx_id", sa.String(), nullable=True),
        sa.Column("prior_soft_cap", sa.Numeric(precision=12, scale=2), nullable=False, server_default="17600.00"),
        sa.Column("monthly_loc_reduction", sa.Numeric(precision=12, scale=2), nullable=False, server_default="400.00"),
        sa.Column("tax_liability", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("actual_loc_balance", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monthly_checklists_year_month", "monthly_checklists", ["year_month"], unique=True)


def downgrade() -> None:
    """Drop monthly_checklists and checklist_configs tables."""
    op.drop_index("ix_monthly_checklists_year_month", table_name="monthly_checklists")
    op.drop_table("monthly_checklists")
    op.drop_table("checklist_configs")
