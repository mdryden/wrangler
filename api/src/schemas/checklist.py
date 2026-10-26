from __future__ import annotations

import calendar
import datetime
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .company import WaveAccountItem


class ChecklistConfigResponse(BaseModel):
    company_id: uuid.UUID | None = None
    company_name: str | None = None
    is_wave_connected: bool = False
    chequing_wave_account_id: str | None = None
    chequing_wave_account_name: str | None = None
    mastercard_wave_account_id: str | None = None
    mastercard_wave_account_name: str | None = None
    tax_expense_wave_account_id: str | None = None
    tax_expense_wave_account_name: str | None = None
    tax_payable_wave_account_id: str | None = None
    tax_payable_wave_account_name: str | None = None
    wave_web_business_slug: str = "d2977f10-6793-4504-a139-f0d6872b2628"
    last_chequing_tx_date: datetime.date | None = None
    last_mastercard_tx_date: datetime.date | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def extract_company_fields(cls, data: Any) -> Any:
        if hasattr(data, "__dict__") and not isinstance(data, dict):
            company = getattr(data, "company", None)
            company_name = company.name if company else None
            is_wave_connected = bool(company and company.wave_api_token and company.wave_business_id)
            return {
                "company_id": getattr(data, "company_id", None),
                "company_name": company_name,
                "is_wave_connected": is_wave_connected,
                "chequing_wave_account_id": getattr(data, "chequing_wave_account_id", None),
                "chequing_wave_account_name": getattr(data, "chequing_wave_account_name", None),
                "mastercard_wave_account_id": getattr(data, "mastercard_wave_account_id", None),
                "mastercard_wave_account_name": getattr(data, "mastercard_wave_account_name", None),
                "tax_expense_wave_account_id": getattr(data, "tax_expense_wave_account_id", None),
                "tax_expense_wave_account_name": getattr(data, "tax_expense_wave_account_name", None),
                "tax_payable_wave_account_id": getattr(data, "tax_payable_wave_account_id", None),
                "tax_payable_wave_account_name": getattr(data, "tax_payable_wave_account_name", None),
                "wave_web_business_slug": getattr(data, "wave_web_business_slug", "d2977f10-6793-4504-a139-f0d6872b2628"),
                "last_chequing_tx_date": getattr(data, "last_chequing_tx_date", None),
                "last_mastercard_tx_date": getattr(data, "last_mastercard_tx_date", None),
            }
        return data


class ChecklistConfigUpdate(BaseModel):
    company_id: uuid.UUID | None = None
    chequing_wave_account_id: str | None = None
    chequing_wave_account_name: str | None = None
    mastercard_wave_account_id: str | None = None
    mastercard_wave_account_name: str | None = None
    tax_expense_wave_account_id: str | None = None
    tax_expense_wave_account_name: str | None = None
    tax_payable_wave_account_id: str | None = None
    tax_payable_wave_account_name: str | None = None
    wave_web_business_slug: str | None = None
    last_chequing_tx_date: datetime.date | None = None
    last_mastercard_tx_date: datetime.date | None = None


class WaveAccountsGroupedResponse(BaseModel):
    bank_and_cc_accounts: list[WaveAccountItem] = Field(default_factory=list)
    expense_accounts: list[WaveAccountItem] = Field(default_factory=list)
    liability_accounts: list[WaveAccountItem] = Field(default_factory=list)


def calculate_wave_cash_flow_url(slug: str, year_month: str) -> str:
    parts = year_month.split("-")
    year, month = int(parts[0]), int(parts[1])
    last_day = calendar.monthrange(year, month)[1]
    return f"https://next.waveapps.com/{slug}/reports/cash-flow?end={year_month}-{last_day:02d}&start={year_month}-01"


class MonthlyChecklistResponse(BaseModel):
    id: uuid.UUID
    year_month: str
    completed_steps: list[str] = Field(default_factory=list)
    net_operating_cash: Decimal | None = None
    tax_rate: Decimal
    tax_reserve_amount: Decimal | None = None
    tax_accrual_wave_tx_id: str | None = None
    prior_soft_cap: Decimal
    monthly_loc_reduction: Decimal
    current_soft_cap: Decimal
    tax_liability: Decimal | None = None
    actual_loc_balance: Decimal | None = None
    maximum_safe_draw: Decimal | None = None
    wave_cash_flow_url: str

    model_config = ConfigDict(from_attributes=True)


class MonthlyChecklistUpdate(BaseModel):
    completed_steps: list[str] | None = None
    net_operating_cash: Decimal | None = None
    tax_rate: Decimal | None = None
    prior_soft_cap: Decimal | None = None
    monthly_loc_reduction: Decimal | None = None
    tax_liability: Decimal | None = None
    actual_loc_balance: Decimal | None = None


class RbcCsvSyncResponse(BaseModel):
    total_rows: int = 0
    synced_count: int = 0
    failed_count: int = 0
    auto_categorized_count: int = 0
    uncategorized_count: int = 0
    latest_transaction_date: datetime.date | None = None
    errors: list[str] = Field(default_factory=list)


class TaxAccrualSyncRequest(BaseModel):
    net_operating_cash: Decimal | None = None
    tax_rate: Decimal | None = None
