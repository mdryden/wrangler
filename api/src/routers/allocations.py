import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.allocation import Allocation
from models.wave_category import WaveCategory
from schemas.allocation import AllocationCategoryUpdateRequest, AllocationResponse, LockUpdateRequest

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
