from __future__ import annotations

import calendar
import datetime
import re
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.checklist import ChecklistConfig, MonthlyChecklist
from models.company import Company
from models.wave_category import WaveCategory
from schemas.checklist import (
    ChecklistConfigUpdate,
    RbcCsvSyncResponse,
    calculate_wave_cash_flow_url,
)
from services.wave.client import WaveClient

from .rbc_parser import parse_rbc_csv, resolve_category_for_row


def get_or_create_config(db: Session) -> ChecklistConfig:
    config = db.get(ChecklistConfig, 1)
    if config is None:
        config = ChecklistConfig(id=1)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def update_config(db: Session, update_data: ChecklistConfigUpdate) -> ChecklistConfig:
    config = get_or_create_config(db)
    payload = update_data.model_dump(exclude_unset=True)
    for field, val in payload.items():
        setattr(config, field, val)
    db.commit()
    db.refresh(config)
    return config


def validate_year_month(year_month: str) -> None:
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", year_month):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid year_month format '{year_month}', expected YYYY-MM",
        )


def get_or_create_monthly_checklist(db: Session, year_month: str, config: ChecklistConfig) -> MonthlyChecklist:
    validate_year_month(year_month)

    stmt = select(MonthlyChecklist).where(MonthlyChecklist.year_month == year_month)
    checklist = db.scalar(stmt)
    if checklist is not None:
        return checklist

    # Carry forward from the latest previous month if one exists
    prior_stmt = select(MonthlyChecklist).where(MonthlyChecklist.year_month < year_month).order_by(MonthlyChecklist.year_month.desc()).limit(1)
    prior_record = db.scalar(prior_stmt)

    if prior_record is not None:
        prior_soft_cap = prior_record.current_soft_cap
        monthly_loc_reduction = prior_record.monthly_loc_reduction
        tax_rate = prior_record.tax_rate
    else:
        prior_soft_cap = Decimal("17600.00")
        monthly_loc_reduction = Decimal("400.00")
        tax_rate = Decimal("12.00")

    checklist = MonthlyChecklist(
        year_month=year_month,
        prior_soft_cap=prior_soft_cap,
        monthly_loc_reduction=monthly_loc_reduction,
        tax_rate=tax_rate,
    )
    db.add(checklist)
    db.commit()
    db.refresh(checklist)
    return checklist


def build_wave_cash_flow_url(slug: str, year_month: str) -> str:
    return calculate_wave_cash_flow_url(slug, year_month)


async def sync_rbc_feed_to_wave(
    db: Session,
    year_month: str,
    account_type: str,
    file_bytes: bytes,
) -> RbcCsvSyncResponse:
    validate_year_month(year_month)
    config = get_or_create_config(db)

    acc_type_lower = account_type.strip().lower()
    if acc_type_lower not in ("chequing", "mastercard"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported account_type: '{account_type}', expected 'chequing' or 'mastercard'",
        )

    if not config.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Checklist company is not configured in Checklist Settings",
        )

    company = db.get(Company, config.company_id)
    if not company or not company.wave_api_token or not company.wave_business_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configured company is not connected to Wave",
        )

    if acc_type_lower == "chequing":
        anchor_account_id = config.chequing_wave_account_id
        if not anchor_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RBC Chequing Wave account is not configured in Checklist Settings",
            )
        expected_type_header = "Chequing"
    else:
        anchor_account_id = config.mastercard_wave_account_id
        if not anchor_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RBC Mastercard Wave account is not configured in Checklist Settings",
            )
        expected_type_header = "MasterCard"

    try:
        normalized_rows = parse_rbc_csv(file_bytes, expected_account_type=expected_type_header)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not normalized_rows:
        return RbcCsvSyncResponse(total_rows=0, synced_count=0)

    cats_stmt = select(WaveCategory).where(WaveCategory.company_id == company.id)
    wave_categories = list(db.scalars(cats_stmt).all())

    uncat_inc = next(
        (c for c in wave_categories if c.is_uncategorized and (c.account_subtype == "UNCATEGORIZED_INCOME" or c.account_type in ("REVENUE", "INCOME"))),
        None,
    )

    synced_count = 0
    failed_count = 0
    auto_categorized_count = 0
    uncategorized_count = 0
    errors: list[str] = []
    max_csv_date: datetime.date | None = None

    for row in normalized_rows:
        cat_id, is_auto = resolve_category_for_row(row, wave_categories)
        if is_auto:
            auto_categorized_count += 1
        else:
            uncategorized_count += 1

        external_id = f"wrangler_rbc_{acc_type_lower}_{row.date}_{row.row_index}_{abs(row.signed_amount)}"

        if row.signed_amount < Decimal("0"):
            anchor_direction = "WITHDRAWAL"
            line_balance = "INCREASE"
        else:
            anchor_direction = "DEPOSIT"
            if uncat_inc and cat_id == uncat_inc.wave_account_id:
                line_balance = "INCREASE"
            else:
                line_balance = "DECREASE"

        try:
            await WaveClient.create_money_transaction(
                token=company.wave_api_token,
                business_id=company.wave_business_id,
                external_id=external_id,
                date=str(row.date),
                description=row.description,
                amount=abs(row.signed_amount),
                anchor_account_id=anchor_account_id,
                category_account_id=cat_id,
                anchor_direction=anchor_direction,
                line_balance=line_balance,
            )
            synced_count += 1
            if max_csv_date is None or row.date > max_csv_date:
                max_csv_date = row.date
        except Exception as exc:
            failed_count += 1
            errors.append(f"Row {row.row_index} ({row.date} {row.description}): {str(exc)}")

    # Update last transaction date if synced rows exist
    if max_csv_date is not None:
        if acc_type_lower == "chequing":
            if config.last_chequing_tx_date is None or max_csv_date > config.last_chequing_tx_date:
                config.last_chequing_tx_date = max_csv_date
        else:
            if config.last_mastercard_tx_date is None or max_csv_date > config.last_mastercard_tx_date:
                config.last_mastercard_tx_date = max_csv_date

    # Update MonthlyChecklist completed_steps
    monthly_checklist = get_or_create_monthly_checklist(db, year_month, config)
    step_key = "import_chequing" if acc_type_lower == "chequing" else "import_mastercard"
    steps = list(monthly_checklist.completed_steps)
    if step_key not in steps:
        steps.append(step_key)
        monthly_checklist.completed_steps = steps

    db.commit()

    return RbcCsvSyncResponse(
        total_rows=len(normalized_rows),
        synced_count=synced_count,
        failed_count=failed_count,
        auto_categorized_count=auto_categorized_count,
        uncategorized_count=uncategorized_count,
        latest_transaction_date=max_csv_date,
        errors=errors,
    )


async def sync_tax_accrual_to_wave(
    db: Session,
    year_month: str,
    net_operating_cash: Decimal | None = None,
    tax_rate: Decimal | None = None,
) -> MonthlyChecklist:
    validate_year_month(year_month)
    config = get_or_create_config(db)

    if not config.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Checklist company is not configured in Checklist Settings",
        )

    company = db.get(Company, config.company_id)
    if not company or not company.wave_api_token or not company.wave_business_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configured company is not connected to Wave",
        )

    if not config.tax_expense_wave_account_id or not config.tax_payable_wave_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tax Expense and Tax Payable accounts must both be configured in Checklist Settings",
        )

    monthly_checklist = get_or_create_monthly_checklist(db, year_month, config)

    if net_operating_cash is not None:
        monthly_checklist.net_operating_cash = net_operating_cash
    if tax_rate is not None:
        monthly_checklist.tax_rate = tax_rate

    tax_reserve = monthly_checklist.tax_reserve_amount
    if tax_reserve is None or tax_reserve <= Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tax reserve amount must be greater than $0.00 to post a journal entry",
        )

    parts = year_month.split("-")
    year, month = int(parts[0]), int(parts[1])
    last_day = calendar.monthrange(year, month)[1]
    date_str = f"{year_month}-{last_day:02d}"

    wave_tx_id = await WaveClient.create_money_transaction(
        token=company.wave_api_token,
        business_id=company.wave_business_id,
        external_id=f"wrangler_tax_accrual_{company.id}_{year_month}",
        date=date_str,
        description=f"Corporate Tax Accrual ({year_month})",
        amount=tax_reserve,
        anchor_account_id=config.tax_payable_wave_account_id,
        category_account_id=config.tax_expense_wave_account_id,
        anchor_direction="WITHDRAWAL",
        line_balance="INCREASE",
    )

    monthly_checklist.tax_accrual_wave_tx_id = wave_tx_id
    steps = list(monthly_checklist.completed_steps)
    if "calculate_net_cash_and_tax" not in steps:
        steps.append("calculate_net_cash_and_tax")
        monthly_checklist.completed_steps = steps

    db.commit()
    db.refresh(monthly_checklist)
    return monthly_checklist
