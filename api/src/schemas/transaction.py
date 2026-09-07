import datetime
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from .allocation import AllocationCreateItem, AllocationResponse


class TransactionCreate(BaseModel):
    company_id: uuid.UUID
    date: datetime.date
    description: str
    total_amount: Decimal
    currency_code: str = "USD"
    source: str = "manual"
    external_id: str | None = None
    receipt_file_path: str | None = None
    allocations: list[AllocationCreateItem] | None = None

    @field_validator("external_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("description")
    @classmethod
    def validate_description_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be empty")
        return v

    @field_validator("total_amount")
    @classmethod
    def validate_total_amount_non_zero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("total_amount must be strictly non-zero")
        return v


class TransactionUpdate(BaseModel):
    date: datetime.date | None = None
    description: str | None = None
    total_amount: Decimal | None = None
    currency_code: str | None = None
    source: str | None = None
    external_id: str | None = None
    receipt_file_path: str | None = None

    @field_validator("external_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("description")
    @classmethod
    def validate_description_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("description must not be empty")
        return v

    @field_validator("total_amount")
    @classmethod
    def validate_total_amount_non_zero(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v == 0:
            raise ValueError("total_amount must be strictly non-zero")
        return v


class TransactionResponse(BaseModel):
    id: uuid.UUID
    source: str
    external_id: str | None = None
    date: datetime.date
    description: str
    total_amount: Decimal
    currency_code: str
    receipt_file_path: str | None = None
    allocations: list[AllocationResponse] = []

    model_config = ConfigDict(from_attributes=True)


class PaginatedTransactionsResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
