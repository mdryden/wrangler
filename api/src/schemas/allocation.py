import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


class AllocationResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    amount: Decimal
    is_personal: bool
    company_id: uuid.UUID | None = None
    is_locked: bool = False
    wave_category_id: uuid.UUID | None = None
    wave_transaction_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AllocationItem(BaseModel):
    id: uuid.UUID | None = None
    amount: Decimal
    is_personal: bool = False
    company_id: uuid.UUID | None = None
    is_locked: bool = False
    wave_category_id: uuid.UUID | None = None
    wave_transaction_id: str | None = None


class AllocationCreateItem(BaseModel):
    id: uuid.UUID | None = None
    amount: Decimal
    is_personal: bool = False
    company_id: uuid.UUID | None = None
    is_locked: bool = False
    wave_category_id: uuid.UUID | None = None
    wave_transaction_id: str | None = None


class AllocationUpdateRequest(BaseModel):
    allocations: list[AllocationItem]


class AllocationCategoryUpdateRequest(BaseModel):
    wave_category_id: uuid.UUID | None = None


class LockUpdateRequest(BaseModel):
    is_locked: bool


class BulkAllocationCategoryUpdateRequest(BaseModel):
    allocation_ids: list[uuid.UUID]
    wave_category_id: uuid.UUID

    @field_validator("allocation_ids")
    @classmethod
    def validate_non_empty(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if not v:
            raise ValueError("allocation_ids list cannot be empty")
        return v


class BulkAllocationCategoryUpdateResponse(BaseModel):
    updated_count: int
    allocation_ids: list[uuid.UUID]
