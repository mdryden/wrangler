from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from database import get_db
from models.checklist import MonthlyChecklist
from models.company import Company
from schemas.checklist import (
    ChecklistConfigResponse,
    ChecklistConfigUpdate,
    MonthlyChecklistResponse,
    MonthlyChecklistUpdate,
    RbcCsvSyncResponse,
    TaxAccrualSyncRequest,
    WaveAccountsGroupedResponse,
    calculate_wave_cash_flow_url,
)
from schemas.company import WaveAccountItem
from services.checklist.service import (
    get_or_create_config,
    get_or_create_monthly_checklist,
    sync_rbc_feed_to_wave,
    sync_tax_accrual_to_wave,
    update_config,
    validate_year_month,
)
from services.wave.client import WaveApiError, WaveAuthError, WaveClient

router = APIRouter(prefix="/api/checklist", tags=["checklist"])


def _format_monthly_checklist_response(checklist: MonthlyChecklist, slug: str) -> MonthlyChecklistResponse:
    url = calculate_wave_cash_flow_url(slug, checklist.year_month)
    return MonthlyChecklistResponse(
        id=checklist.id,
        year_month=checklist.year_month,
        completed_steps=checklist.completed_steps,
        net_operating_cash=checklist.net_operating_cash,
        tax_rate=checklist.tax_rate,
        tax_reserve_amount=checklist.tax_reserve_amount,
        tax_accrual_wave_tx_id=checklist.tax_accrual_wave_tx_id,
        prior_soft_cap=checklist.prior_soft_cap,
        monthly_loc_reduction=checklist.monthly_loc_reduction,
        current_soft_cap=checklist.current_soft_cap,
        tax_liability=checklist.tax_liability,
        actual_loc_balance=checklist.actual_loc_balance,
        maximum_safe_draw=checklist.maximum_safe_draw,
        wave_cash_flow_url=url,
    )


@router.get("/config", response_model=ChecklistConfigResponse)
def get_checklist_config(db: Annotated[Session, Depends(get_db)]) -> ChecklistConfigResponse:
    """Retrieve singleton checklist configuration."""
    config = get_or_create_config(db)
    return ChecklistConfigResponse.model_validate(config)


@router.put("/config", response_model=ChecklistConfigResponse)
def update_checklist_config(
    payload: ChecklistConfigUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> ChecklistConfigResponse:
    """Update singleton checklist configuration."""
    config = update_config(db, payload)
    return ChecklistConfigResponse.model_validate(config)


@router.get("/wave-accounts/{company_id}", response_model=WaveAccountsGroupedResponse)
async def get_grouped_wave_accounts(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> WaveAccountsGroupedResponse:
    """Retrieve Chart of Accounts grouped for checklist settings dropdowns."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    if not (company.wave_api_token and company.wave_business_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company is not connected to Wave",
        )

    try:
        res = await WaveClient.get_business_accounts(company.wave_api_token, company.wave_business_id)
    except WaveAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except WaveApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    bank_and_cc = [
        WaveAccountItem(
            id=a.id,
            name=a.name,
            type=a.type,
            subtype=a.subtype,
            is_uncategorized=a.is_uncategorized,
        )
        for a in res.anchor_accounts
    ]

    expenses = [
        WaveAccountItem(
            id=c.id,
            name=c.name,
            type=c.type,
            subtype=c.subtype,
            is_uncategorized=c.is_uncategorized,
        )
        for c in res.expense_categories
        if c.type == "EXPENSE"
    ]

    liabilities = [
        WaveAccountItem(
            id=liab.id,
            name=liab.name,
            type=liab.type,
            subtype=liab.subtype,
            is_uncategorized=liab.is_uncategorized,
        )
        for liab in res.liability_accounts
    ]

    return WaveAccountsGroupedResponse(
        bank_and_cc_accounts=bank_and_cc,
        expense_accounts=expenses,
        liability_accounts=liabilities,
    )


@router.get("/months/{year_month}", response_model=MonthlyChecklistResponse)
def get_monthly_checklist(
    year_month: str,
    db: Annotated[Session, Depends(get_db)],
) -> MonthlyChecklistResponse:
    """Retrieve or initialize monthly checklist record with carry-forward defaults."""
    config = get_or_create_config(db)
    checklist = get_or_create_monthly_checklist(db, year_month, config)
    return _format_monthly_checklist_response(checklist, config.wave_web_business_slug)


@router.patch("/months/{year_month}", response_model=MonthlyChecklistResponse)
def patch_monthly_checklist(
    year_month: str,
    payload: MonthlyChecklistUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> MonthlyChecklistResponse:
    """Update editable fields on a monthly checklist and recalculate derived metrics."""
    validate_year_month(year_month)
    config = get_or_create_config(db)
    checklist = get_or_create_monthly_checklist(db, year_month, config)

    dumped = payload.model_dump(exclude_unset=True)
    if "completed_steps" in dumped and dumped["completed_steps"] is not None:
        checklist.completed_steps = dumped["completed_steps"]
        del dumped["completed_steps"]

    for field, val in dumped.items():
        setattr(checklist, field, val)

    db.commit()
    db.refresh(checklist)
    return _format_monthly_checklist_response(checklist, config.wave_web_business_slug)


@router.post("/months/{year_month}/sync-rbc-csv", response_model=RbcCsvSyncResponse)
async def sync_rbc_csv(
    year_month: str,
    account_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
) -> RbcCsvSyncResponse:
    """Parse and sync an RBC Chequing or Mastercard CSV export directly to Wave."""
    file_bytes = await file.read()
    return await sync_rbc_feed_to_wave(db, year_month, account_type, file_bytes)


@router.post("/months/{year_month}/sync-tax-accrual", response_model=MonthlyChecklistResponse)
async def sync_tax_accrual(
    year_month: str,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[TaxAccrualSyncRequest | None, Body()] = None,
) -> MonthlyChecklistResponse:
    """Post corporate tax accrual journal entry to Wave for the target month."""
    config = get_or_create_config(db)
    net_operating_cash = payload.net_operating_cash if payload else None
    tax_rate = payload.tax_rate if payload else None

    checklist = await sync_tax_accrual_to_wave(
        db=db,
        year_month=year_month,
        net_operating_cash=net_operating_cash,
        tax_rate=tax_rate,
    )
    return _format_monthly_checklist_response(checklist, config.wave_web_business_slug)
