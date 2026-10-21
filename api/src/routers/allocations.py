import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.allocation import Allocation
from models.wave_category import WaveCategory
from schemas.allocation import (
    AllocationCategoryUpdateRequest,
    AllocationResponse,
    BulkAllocationCategoryUpdateRequest,
    BulkAllocationCategoryUpdateResponse,
    LockUpdateRequest,
)

router = APIRouter(prefix="/api/allocations", tags=["allocations"])


@router.put("/{allocation_id}/lock", response_model=AllocationResponse)
def update_allocation_lock(
    allocation_id: uuid.UUID,
    payload: LockUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Allocation:
    """Lock or unlock a single allocation."""
    allocation = db.get(Allocation, allocation_id)
    if allocation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation with ID '{allocation_id}' not found",
        )

    allocation.is_locked = payload.is_locked
    if not payload.is_locked:
        allocation.wave_transaction_id = None
    db.add(allocation)
    db.commit()
    db.refresh(allocation)

    return allocation


@router.patch("/{allocation_id}/category", response_model=AllocationResponse)
def update_allocation_category(
    allocation_id: uuid.UUID,
    payload: AllocationCategoryUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Allocation:
    """Update wave_category_id on an unlocked allocation."""
    allocation = db.get(Allocation, allocation_id)
    if allocation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation with ID '{allocation_id}' not found",
        )

    if allocation.is_locked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change category on a locked allocation",
        )

    if payload.wave_category_id is not None:
        category = db.get(WaveCategory, payload.wave_category_id)
        if category is None or category.company_id != allocation.company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category for this company",
            )

    allocation.wave_category_id = payload.wave_category_id
    db.add(allocation)
    db.commit()
    db.refresh(allocation)

    return allocation


@router.post("/bulk-category", response_model=BulkAllocationCategoryUpdateResponse)
def update_allocations_bulk_category(
    payload: BulkAllocationCategoryUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> BulkAllocationCategoryUpdateResponse:
    # 1. Fetch category
    category = db.get(WaveCategory, payload.wave_category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"WaveCategory with ID '{payload.wave_category_id}' not found",
        )

    # 2. Fetch allocations
    stmt = select(Allocation).where(Allocation.id.in_(payload.allocation_ids))
    allocations = list(db.scalars(stmt).all())

    if len(allocations) != len(payload.allocation_ids):
        found_ids = {a.id for a in allocations}
        missing_ids = [str(aid) for aid in payload.allocation_ids if aid not in found_ids]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocations not found: {', '.join(missing_ids)}",
        )

    # 3. Guard validations (atomic all-or-nothing)
    for alloc in allocations:
        if alloc.is_locked:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Allocation {alloc.id} is locked and cannot be modified",
            )
        if alloc.is_personal or alloc.company_id != category.company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Allocation {alloc.id} does not belong to the category's company",
            )

    # 4. Atomic update
    for alloc in allocations:
        alloc.wave_category_id = payload.wave_category_id
        db.add(alloc)

    db.commit()

    return BulkAllocationCategoryUpdateResponse(
        updated_count=len(allocations),
        allocation_ids=[alloc.id for alloc in allocations],
    )
