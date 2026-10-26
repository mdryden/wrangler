from __future__ import annotations

import datetime
import json
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from .company import Company


class ChecklistConfig(Base):
    __tablename__ = "checklist_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    chequing_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    chequing_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    mastercard_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    mastercard_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_expense_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_expense_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_payable_wave_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_payable_wave_account_name: Mapped[str | None] = mapped_column(String, nullable=True)
    wave_web_business_slug: Mapped[str] = mapped_column(String, nullable=False, default="d2977f10-6793-4504-a139-f0d6872b2628")
    last_chequing_tx_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    last_mastercard_tx_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)

    company: Mapped[Company | None] = relationship("Company")


class MonthlyChecklist(Base):
    __tablename__ = "monthly_checklists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    year_month: Mapped[str] = mapped_column(String(7), unique=True, index=True, nullable=False)
    completed_steps_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")

    net_operating_cash: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("12.00"))
    tax_accrual_wave_tx_id: Mapped[str | None] = mapped_column(String, nullable=True)

    prior_soft_cap: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("17600.00"))
    monthly_loc_reduction: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("400.00"))
    tax_liability: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    actual_loc_balance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    @property
    def completed_steps(self) -> list[str]:
        if not self.completed_steps_json:
            return []
        try:
            return json.loads(self.completed_steps_json)
        except Exception:
            return []

    @completed_steps.setter
    def completed_steps(self, steps: list[str]) -> None:
        self.completed_steps_json = json.dumps(steps)

    @property
    def tax_reserve_amount(self) -> Decimal | None:
        if self.net_operating_cash is None:
            return None
        net_cash = Decimal(str(self.net_operating_cash))
        if net_cash <= Decimal("0.00"):
            return Decimal("0.00")
        rate = Decimal(str(self.tax_rate))
        return (net_cash * (rate / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def current_soft_cap(self) -> Decimal:
        prior = Decimal(str(self.prior_soft_cap))
        reduction = Decimal(str(self.monthly_loc_reduction))
        return (prior - reduction).quantize(Decimal("0.01"))

    @property
    def maximum_safe_draw(self) -> Decimal | None:
        if self.tax_liability is None or self.actual_loc_balance is None:
            return None
        tax_liab = Decimal(str(self.tax_liability))
        loc_bal = Decimal(str(self.actual_loc_balance))
        return (self.current_soft_cap - tax_liab - loc_bal).quantize(Decimal("0.01"))
