import datetime
import io
import os
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager, joinedload

from database import get_db
from models.allocation import Allocation
from models.company import Company
from models.staged_allocation import StagedAllocation
from models.transaction import Transaction
from models.wave_category import WaveCategory
from schemas.allocation import AllocationResponse
from schemas.company import (
    CompanyCreate,
    CompanyLockBatchRequest,
    CompanyResponse,
    CompanyUpdate,
    WaveAccountItem,
    WaveBusinessAccountsRequest,
    WaveBusinessAccountsResponse,
    WaveBusinessItem,
    WaveCategoryResponse,
    WaveConnectRequest,
    WaveSyncBatchRequest,
    WaveSyncErrorItem,
    WaveSyncResponse,
    WaveTestTokenRequest,
)
from services.export import generate_wave_csv
from services.wave.client import WaveApiError, WaveAuthError, WaveClient

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _get_company_metrics(db: Session, company_id: uuid.UUID) -> dict[str, int | Decimal]:
    stmt = select(
        func.count(func.distinct(Allocation.transaction_id)).label("tx_count"),
        func.coalesce(func.sum(case((Allocation.is_locked.is_(False), 1), else_=0)), 0).label("unlocked_count"),
        func.coalesce(
            func.sum(case((Allocation.is_locked.is_(False), Allocation.amount), else_=Decimal("0.00"))),
            Decimal("0.00"),
        ).label("unlocked_total"),
        func.coalesce(func.sum(case((Allocation.is_locked.is_(True), 1), else_=0)), 0).label("locked_count"),
    ).where(
        Allocation.company_id == company_id,
        Allocation.is_personal.is_(False),
    )
    row = db.execute(stmt).one()
    unlocked_total = Decimal(str(row.unlocked_total or 0)).quantize(Decimal("0.01"))
    return {
        "transaction_count": int(row.tx_count or 0),
        "unlocked_allocation_count": int(row.unlocked_count or 0),
        "unlocked_amount_total": unlocked_total,
        "locked_allocation_count": int(row.locked_count or 0),
    }


def _format_company_response(company: Company, metrics: dict[str, int | Decimal]) -> dict:
    is_wave_connected = bool(company.wave_api_token and company.wave_business_id and company.wave_anchor_account_id)
    return {
        "id": company.id,
        "name": company.name,
        "wave_business_id": company.wave_business_id,
        "wave_business_name": company.wave_business_name,
        "wave_anchor_account_id": company.wave_anchor_account_id,
        "is_wave_connected": is_wave_connected,
        **metrics,
    }


def _sync_categories_for_company(
    db: Session,
    company_id: uuid.UUID,
    expense_categories: list,
    remove_missing: bool = False,
) -> None:
    existing_stmt = select(WaveCategory).where(WaveCategory.company_id == company_id)
    existing_cats = {c.wave_account_id: c for c in db.scalars(existing_stmt).all()}

    incoming_account_ids = set()
    for cat in expense_categories:
        incoming_account_ids.add(cat.id)
        if cat.id in existing_cats:
            existing = existing_cats[cat.id]
            existing.name = cat.name
            existing.account_type = cat.type
            existing.account_subtype = cat.subtype
            existing.is_uncategorized = cat.is_uncategorized
        else:
            new_cat = WaveCategory(
                company_id=company_id,
                wave_account_id=cat.id,
                name=cat.name,
                account_type=cat.type,
                account_subtype=cat.subtype,
                is_uncategorized=cat.is_uncategorized,
            )
            db.add(new_cat)

    if remove_missing:
        for account_id, existing in existing_cats.items():
            if account_id not in incoming_account_ids:
                db.delete(existing)


@router.post("/wave/test-token", response_model=list[WaveBusinessItem])
async def test_wave_token(payload: WaveTestTokenRequest) -> list[WaveBusinessItem]:
    """Verify Full Access Token against Wave and return accessible businesses."""
    try:
        businesses = await WaveClient.get_user_businesses(payload.token)
    except WaveAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except WaveApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return [WaveBusinessItem(id=b.id, name=b.name, is_personal=b.is_personal) for b in businesses]


@router.post("/wave/business-accounts", response_model=WaveBusinessAccountsResponse)
async def get_wave_business_accounts(payload: WaveBusinessAccountsRequest) -> WaveBusinessAccountsResponse:
    """Fetch Chart of Accounts for a Wave business, returning anchor candidates and active expense categories."""
    try:
        accounts_result = await WaveClient.get_business_accounts(payload.token, payload.business_id)
    except WaveAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except WaveApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return WaveBusinessAccountsResponse(
        anchor_accounts=[
            WaveAccountItem(
                id=a.id,
                name=a.name,
                type=a.type,
                subtype=a.subtype,
                is_uncategorized=a.is_uncategorized,
            )
            for a in accounts_result.anchor_accounts
        ],
        expense_categories=[
            WaveAccountItem(
                id=c.id,
                name=c.name,
                type=c.type,
                subtype=c.subtype,
                is_uncategorized=c.is_uncategorized,
            )
            for c in accounts_result.expense_categories
        ],
    )


@router.get("", response_model=list[CompanyResponse])
def list_companies(db: Annotated[Session, Depends(get_db)]) -> list[dict]:
    """Retrieve all companies ordered by name with allocated transaction count and export summary statistics."""
    stats_subq = (
        select(
            Allocation.company_id.label("comp_id"),
            func.count(func.distinct(Allocation.transaction_id)).label("tx_count"),
            func.coalesce(func.sum(case((Allocation.is_locked.is_(False), 1), else_=0)), 0).label("unlocked_count"),
            func.coalesce(
                func.sum(case((Allocation.is_locked.is_(False), Allocation.amount), else_=Decimal("0.00"))),
                Decimal("0.00"),
            ).label("unlocked_total"),
            func.coalesce(func.sum(case((Allocation.is_locked.is_(True), 1), else_=0)), 0).label("locked_count"),
        )
        .where(Allocation.company_id.is_not(None), Allocation.is_personal.is_(False))
        .group_by(Allocation.company_id)
        .subquery()
    )
    stmt = (
        select(
            Company,
            func.coalesce(stats_subq.c.tx_count, 0).label("transaction_count"),
            func.coalesce(stats_subq.c.unlocked_count, 0).label("unlocked_allocation_count"),
            func.coalesce(stats_subq.c.unlocked_total, Decimal("0.00")).label("unlocked_amount_total"),
            func.coalesce(stats_subq.c.locked_count, 0).label("locked_allocation_count"),
        )
        .outerjoin(stats_subq, Company.id == stats_subq.c.comp_id)
        .order_by(Company.name)
    )
    results = db.execute(stmt).all()
    return [
        _format_company_response(
            company,
            {
                "transaction_count": int(tx_count or 0),
                "unlocked_allocation_count": int(unlocked_count or 0),
                "unlocked_amount_total": Decimal(str(unlocked_total or 0)).quantize(Decimal("0.01")),
                "locked_allocation_count": int(locked_count or 0),
            },
        )
        for company, tx_count, unlocked_count, unlocked_total, locked_count in results
    ]


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Create a new company record."""
    company = Company(
        name=payload.name,
    )
    db.add(company)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Company with name '{payload.name}' already exists",
        ) from exc
    db.refresh(company)
    return _format_company_response(company, _get_company_metrics(db, company.id))


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Retrieve a single company by ID with allocated transaction count and export summary statistics."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )
    metrics = _get_company_metrics(db, company_id)
    return _format_company_response(company, metrics)


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Update an existing company record."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(company, key, value)

    db.add(company)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Company with name '{payload.name}' already exists",
        ) from exc
    db.refresh(company)
    metrics = _get_company_metrics(db, company_id)
    return _format_company_response(company, metrics)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Delete a company record."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    allocation_count = db.scalar(select(func.count(Allocation.id)).where(Allocation.company_id == company_id))
    staged_allocation_count = db.scalar(select(func.count(StagedAllocation.id)).where(StagedAllocation.company_id == company_id))
    if (allocation_count and allocation_count > 0) or (staged_allocation_count and staged_allocation_count > 0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete company '{company.name}': linked to existing allocations",
        )

    db.delete(company)
    db.commit()


@router.post("/{company_id}/wave/connect", response_model=CompanyResponse)
async def connect_company_wave(
    company_id: uuid.UUID,
    payload: WaveConnectRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Save Wave connection credentials on the company and populate cached expense categories."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    try:
        accounts_result = await WaveClient.get_business_accounts(payload.token, payload.business_id)
    except WaveAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except WaveApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    company.wave_api_token = payload.token
    company.wave_business_id = payload.business_id
    company.wave_business_name = payload.business_name
    company.wave_anchor_account_id = payload.anchor_account_id

    _sync_categories_for_company(db, company_id, accounts_result.expense_categories, remove_missing=False)

    db.add(company)
    db.commit()
    db.refresh(company)

    metrics = _get_company_metrics(db, company_id)
    return _format_company_response(company, metrics)


@router.post("/{company_id}/wave/sync-categories", response_model=list[WaveCategoryResponse])
async def sync_company_wave_categories(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> list[WaveCategory]:
    """Synchronize cached expense categories from Wave for the company, upserting active accounts and pruning removed ones."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    if not (company.wave_api_token and company.wave_business_id and company.wave_anchor_account_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company is not connected to Wave",
        )

    try:
        accounts_result = await WaveClient.get_business_accounts(company.wave_api_token, company.wave_business_id)
    except WaveAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except WaveApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    _sync_categories_for_company(db, company_id, accounts_result.expense_categories, remove_missing=True)
    db.commit()

    stmt = (
        select(WaveCategory)
        .where(WaveCategory.company_id == company_id, WaveCategory.account_type == "EXPENSE")
        .order_by(WaveCategory.is_uncategorized.desc(), WaveCategory.name.asc())
    )
    return list(db.scalars(stmt).all())


@router.get("/{company_id}/wave/categories", response_model=list[WaveCategoryResponse])
def get_company_wave_categories(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> list[WaveCategory]:
    """List cached Wave expense categories for the company, with uncategorized expense ordered first."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    stmt = (
        select(WaveCategory)
        .where(WaveCategory.company_id == company_id, WaveCategory.account_type == "EXPENSE")
        .order_by(WaveCategory.is_uncategorized.desc(), WaveCategory.name.asc())
    )
    return list(db.scalars(stmt).all())


@router.delete("/{company_id}/wave", response_model=CompanyResponse)
def disconnect_company_wave(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Clear Wave connection credentials and remove cached categories, reverting company to CSV export mode."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    company.wave_api_token = None
    company.wave_business_id = None
    company.wave_business_name = None
    company.wave_anchor_account_id = None

    # Delete cached categories
    categories = list(db.scalars(select(WaveCategory).where(WaveCategory.company_id == company_id)).all())
    for cat in categories:
        db.delete(cat)

    db.add(company)
    db.commit()
    db.refresh(company)

    metrics = _get_company_metrics(db, company_id)
    return _format_company_response(company, metrics)


@router.post("/{company_id}/sync-wave", response_model=WaveSyncResponse)
async def sync_company_to_wave(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[WaveSyncBatchRequest | None, Body()] = None,
) -> WaveSyncResponse:
    """Batch synchronize eligible business allocations directly to Wave with atomic per-transaction commits."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    if not (company.wave_api_token and company.wave_business_id and company.wave_anchor_account_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company is not connected to Wave",
        )

    fallback_stmt = select(WaveCategory).where(
        WaveCategory.company_id == company_id,
        WaveCategory.is_uncategorized.is_(True),
    )
    fallback_category = db.scalars(fallback_stmt).first()

    filters = [
        Allocation.company_id == company_id,
        Allocation.is_personal.is_(False),
        Allocation.is_locked.is_(False),
    ]
    if payload is not None and payload.allocation_ids:
        filters.append(Allocation.id.in_(payload.allocation_ids))

    stmt = (
        select(Allocation)
        .join(Allocation.transaction)
        .options(
            contains_eager(Allocation.transaction),
            joinedload(Allocation.wave_category),
        )
        .where(*filters)
        .order_by(Transaction.date.asc(), Transaction.id.asc(), Allocation.id.asc())
    )
    allocations = list(db.scalars(stmt).unique().all())

    for alloc in allocations:
        if alloc.wave_category_id is None and fallback_category is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Allocation {alloc.id} requires a category before syncing",
            )

    synced_count = 0
    failed_count = 0
    errors: list[WaveSyncErrorItem] = []

    for alloc in allocations:
        category_account_id = alloc.wave_category.wave_account_id if alloc.wave_category else fallback_category.wave_account_id

        description = alloc.transaction.description
        notes: str | None = None
        if alloc.transaction.receipt_file_path:
            filename = os.path.basename(alloc.transaction.receipt_file_path)
            notes = f"Receipt: {filename}"

        try:
            wave_tx_id = await WaveClient.create_money_transaction(
                token=company.wave_api_token,
                business_id=company.wave_business_id,
                external_id=f"wrangler_{alloc.id}",
                date=alloc.transaction.date.isoformat(),
                description=description,
                amount=alloc.amount,
                anchor_account_id=company.wave_anchor_account_id,
                category_account_id=category_account_id,
                notes=notes,
            )
            alloc.is_locked = True
            alloc.wave_transaction_id = wave_tx_id
            if alloc.wave_category_id is None and fallback_category is not None:
                alloc.wave_category_id = fallback_category.id
            db.add(alloc)
            db.commit()
            synced_count += 1
        except Exception as exc:
            db.rollback()
            errors.append(
                WaveSyncErrorItem(
                    allocation_id=alloc.id,
                    description=alloc.transaction.description,
                    error=str(exc),
                )
            )
            failed_count += 1

    return WaveSyncResponse(
        total_processed=len(allocations),
        synced_count=synced_count,
        failed_count=failed_count,
        errors=errors,
    )


@router.get("/{company_id}/export-transactions")
def export_company_transactions(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    include_locked: Annotated[bool, Query(description="Include already-locked allocations in export")] = False,
    start_date: Annotated[datetime.date | None, Query(description="Filter by start date (inclusive)")] = None,
    end_date: Annotated[datetime.date | None, Query(description="Filter by end date (inclusive)")] = None,
) -> StreamingResponse:
    """Generate and stream a CSV file download of business allocations for a company and automatically lock exported allocations."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    filters = [
        Allocation.company_id == company_id,
        Allocation.is_personal.is_(False),
    ]
    if not include_locked:
        filters.append(Allocation.is_locked.is_(False))
    if start_date is not None:
        filters.append(Transaction.date >= start_date)
    if end_date is not None:
        filters.append(Transaction.date <= end_date)

    stmt = (
        select(Allocation)
        .join(Allocation.transaction)
        .options(contains_eager(Allocation.transaction))
        .where(*filters)
        .order_by(Transaction.date.asc(), Transaction.id.asc(), Allocation.id.asc())
    )
    allocations = list(db.scalars(stmt).all())

    csv_data = generate_wave_csv(allocations, company_id=company.id)

    # Automatically lock all exported allocations that were unlocked
    needs_commit = False
    for alloc in allocations:
        if not alloc.is_locked:
            alloc.is_locked = True
            db.add(alloc)
            needs_commit = True
    if needs_commit:
        db.commit()

    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in company.name.strip().lower())
    filename = f"{safe_name}_transactions.csv"

    return StreamingResponse(
        io.StringIO(csv_data),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{company_id}/lock-allocations", response_model=list[AllocationResponse])
def lock_company_allocations(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[CompanyLockBatchRequest | None, Body()] = None,
) -> list[Allocation]:
    """Lock business allocations for this company."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    stmt = select(Allocation).where(
        Allocation.company_id == company_id,
        Allocation.is_personal.is_(False),
    )
    if payload is not None and payload.allocation_ids:
        stmt = stmt.where(Allocation.id.in_(payload.allocation_ids))
    else:
        stmt = stmt.where(Allocation.is_locked.is_(False))

    allocations = list(db.scalars(stmt).all())
    for alloc in allocations:
        alloc.is_locked = True
        db.add(alloc)

    db.commit()
    for alloc in allocations:
        db.refresh(alloc)

    return allocations


@router.post("/{company_id}/unlock-allocations", response_model=list[AllocationResponse])
def unlock_company_allocations(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[CompanyLockBatchRequest | None, Body()] = None,
) -> list[Allocation]:
    """Unlock business allocations for this company."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    stmt = select(Allocation).where(
        Allocation.company_id == company_id,
        Allocation.is_personal.is_(False),
    )
    if payload is not None and payload.allocation_ids:
        stmt = stmt.where(Allocation.id.in_(payload.allocation_ids))
    else:
        stmt = stmt.where(Allocation.is_locked.is_(True))

    allocations = list(db.scalars(stmt).all())
    for alloc in allocations:
        alloc.is_locked = False
        alloc.wave_transaction_id = None
        db.add(alloc)

    db.commit()
    for alloc in allocations:
        db.refresh(alloc)

    return allocations
