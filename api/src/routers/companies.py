import datetime
import io
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from database import get_db
from models.allocation import Allocation
from models.company import Company
from models.transaction import Transaction
from schemas.allocation import AllocationResponse
from schemas.company import CompanyCreate, CompanyLockBatchRequest, CompanyResponse, CompanyUpdate
from services.export import generate_wave_csv

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
        {
            "id": company.id,
            "name": company.name,
            "transaction_count": int(tx_count or 0),
            "unlocked_allocation_count": int(unlocked_count or 0),
            "unlocked_amount_total": Decimal(str(unlocked_total or 0)).quantize(Decimal("0.01")),
            "locked_allocation_count": int(locked_count or 0),
        }
        for company, tx_count, unlocked_count, unlocked_total, locked_count in results
    ]


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    db: Annotated[Session, Depends(get_db)],
) -> Company:
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
    return company


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
    return {
        "id": company.id,
        "name": company.name,
        **metrics,
    }


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
    return {
        "id": company.id,
        "name": company.name,
        **metrics,
    }


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
    if allocation_count and allocation_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete company '{company.name}': linked to existing allocations",
        )

    db.delete(company)
    db.commit()


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
        db.add(alloc)

    db.commit()
    for alloc in allocations:
        db.refresh(alloc)

    return allocations
