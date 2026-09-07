import datetime
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from .allocation import AllocationResponse


class TransactionCreate(BaseModel):
    date: datetime.date
    description: str
    total_amount: Decimal
    currency_code: str = "USD"
    source: str = "manual"
    external_id: str | None = None
    receipt_file_path: str | None = None
    is_approved: bool = False

    @field_validator("external_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v


class TransactionUpdate(BaseModel):
    date: datetime.date | None = None
    description: str | None = None
    total_amount: Decimal | None = None
    currency_code: str | None = None
    source: str | None = None
    external_id: str | None = None
    receipt_file_path: str | None = None
    is_approved: bool | None = None

    @field_validator("external_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v


class TransactionApproveRequest(BaseModel):
    is_approved: bool | None = None


class TransactionResponse(BaseModel):
    id: uuid.UUID
    source: str
    external_id: str | None = None
    date: datetime.date
    description: str
    total_amount: Decimal
    currency_code: str
    receipt_file_path: str | None = None
    is_approved: bool
    allocations: list[AllocationResponse] = []

    model_config = ConfigDict(from_attributes=True)


class PaginatedTransactionsResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
