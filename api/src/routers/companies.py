import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from database import get_db
from models.allocation import Allocation, SyncStatus
from models.company import Company
from models.transaction import Transaction
from schemas.allocation import AllocationResponse
from schemas.company import CompanyCreate, CompanyResponse, CompanySyncStatusBatchRequest, CompanyUpdate
from services.export import generate_wave_csv

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("", response_model=list[CompanyResponse])
def list_companies(db: Annotated[Session, Depends(get_db)]) -> list[dict]:
    """Retrieve all companies ordered by name with allocated transaction count."""
    count_subq = (
        select(
            Allocation.company_id.label("comp_id"),
            func.count(func.distinct(Allocation.transaction_id)).label("tx_count"),
        )
        .where(Allocation.company_id.is_not(None), Allocation.is_personal.is_(False))
        .group_by(Allocation.company_id)
        .subquery()
    )
    stmt = (
        select(Company, func.coalesce(count_subq.c.tx_count, 0).label("transaction_count"))
        .outerjoin(count_subq, Company.id == count_subq.c.comp_id)
        .order_by(Company.name)
    )
    results = db.execute(stmt).all()
    return [
        {
            "id": company.id,
            "name": company.name,
            "transaction_count": tx_count,
        }
        for company, tx_count in results
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
    """Retrieve a single company by ID with allocated transaction count."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )
    tx_count = (
        db.scalar(
            select(func.count(func.distinct(Allocation.transaction_id))).where(
                Allocation.company_id == company_id,
                Allocation.is_personal.is_(False),
            )
        )
        or 0
    )
    return {
        "id": company.id,
        "name": company.name,
        "transaction_count": tx_count,
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
    tx_count = (
        db.scalar(
            select(func.count(func.distinct(Allocation.transaction_id))).where(
                Allocation.company_id == company_id,
                Allocation.is_personal.is_(False),
            )
        )
        or 0
    )
    return {
        "id": company.id,
        "name": company.name,
        "transaction_count": tx_count,
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
    sync_status: Annotated[SyncStatus, Query(alias="status", description="Filter allocations by status (PENDING or SYNCED)")] = SyncStatus.PENDING,
) -> StreamingResponse:
    """Generate and stream a CSV file download of business allocations for a company."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company with ID '{company_id}' not found",
        )

    stmt = (
        select(Allocation)
        .join(Allocation.transaction)
        .options(contains_eager(Allocation.transaction))
        .where(
            Allocation.company_id == company_id,
            Allocation.is_personal.is_(False),
            Allocation.sync_status == sync_status,
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc(), Allocation.id.asc())
    )
    allocations = list(db.scalars(stmt).all())

    csv_data = generate_wave_csv(allocations, company_id=company.id)

    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in company.name.strip().lower())
    filename = f"{safe_name}_{sync_status.value.lower()}_transactions.csv"

    return StreamingResponse(
        io.StringIO(csv_data),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{company_id}/mark-synced", response_model=list[AllocationResponse])
def mark_company_allocations_synced(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[CompanySyncStatusBatchRequest | None, Body()] = None,
) -> list[Allocation]:
    """Mark business allocations for this company as SYNCED."""
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
        stmt = stmt.where(Allocation.sync_status == SyncStatus.PENDING)

    allocations = list(db.scalars(stmt).all())
    for alloc in allocations:
        alloc.sync_status = SyncStatus.SYNCED
        db.add(alloc)

    db.commit()
    for alloc in allocations:
        db.refresh(alloc)

    return allocations


@router.post("/{company_id}/revert-synced", response_model=list[AllocationResponse])
def revert_company_allocations_synced(
    company_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[CompanySyncStatusBatchRequest | None, Body()] = None,
) -> list[Allocation]:
    """Revert business allocations for this company back to PENDING."""
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
        stmt = stmt.where(Allocation.sync_status == SyncStatus.SYNCED)

    allocations = list(db.scalars(stmt).all())
    for alloc in allocations:
        alloc.sync_status = SyncStatus.PENDING
        db.add(alloc)

    db.commit()
    for alloc in allocations:
        db.refresh(alloc)

    return allocations
