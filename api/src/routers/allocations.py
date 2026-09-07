import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.allocation import Allocation, SyncStatus
from schemas.allocation import AllocationResponse

router = APIRouter(prefix="/api/allocations", tags=["allocations"])


@router.put("/{allocation_id}/revert", response_model=AllocationResponse)
def revert_allocation(
    allocation_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Allocation:
    """Revert a single SYNCED allocation back to PENDING."""
    allocation = db.get(Allocation, allocation_id)
    if allocation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allocation with ID '{allocation_id}' not found",
        )

    if allocation.sync_status == SyncStatus.SYNCED:
        allocation.sync_status = SyncStatus.PENDING
        db.add(allocation)
        db.commit()
        db.refresh(allocation)

    return allocation
