import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from models.allocation import SyncStatus


class AllocationResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    amount: Decimal
    is_personal: bool
    company_id: uuid.UUID | None = None
    sync_status: SyncStatus

    model_config = ConfigDict(from_attributes=True)


class AllocationItem(BaseModel):
    id: uuid.UUID | None = None
    amount: Decimal
    is_personal: bool = False
    company_id: uuid.UUID | None = None
    sync_status: SyncStatus = SyncStatus.PENDING


class AllocationCreateItem(BaseModel):
    id: uuid.UUID | None = None
    amount: Decimal
    is_personal: bool = False
    company_id: uuid.UUID | None = None
    sync_status: SyncStatus = SyncStatus.PENDING


class AllocationUpdateRequest(BaseModel):
    allocations: list[AllocationItem]
