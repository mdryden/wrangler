import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.allocation import Allocation
from schemas.allocation import AllocationResponse, LockUpdateRequest

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
    db.add(allocation)
    db.commit()
    db.refresh(allocation)

    return allocation
