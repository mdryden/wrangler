import datetime
import uuid
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from models.staged_transaction import StagedTransaction
from services.importers.registry import get_importer_by_source


class StagedAllocationItem(BaseModel):
    id: uuid.UUID | None = None
    amount: Decimal
    is_personal: bool = False
    company_id: uuid.UUID | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount_non_zero(cls, v: Decimal) -> Decimal:
        if v == Decimal("0"):
            raise ValueError("amount must be strictly non-zero")
        return v


class StagedAllocationResponse(BaseModel):
    id: uuid.UUID
    staged_transaction_id: uuid.UUID
    amount: Decimal
    is_personal: bool
    company_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class StagedTransactionUpdate(BaseModel):
    date: datetime.date | None = None
    description: str | None = None
    total_amount: Decimal | None = None
    url: str | None = None
    allocations: list[StagedAllocationItem] | None = None
    remove_receipt: bool = False

    @field_validator("url")
    @classmethod
    def clean_url(cls, v: str | None) -> str | None:
        if v is not None:
            cleaned = v.strip().strip('"').strip("'").strip()
            return cleaned if cleaned else None
        return v

    @field_validator("description")
    @classmethod
    def validate_description_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("description must not be empty")
            return cleaned
        return v

    @field_validator("total_amount")
    @classmethod
    def validate_total_amount_non_zero(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v == Decimal("0"):
            raise ValueError("total_amount must be strictly non-zero")
        return v


class StagedTransactionResponse(BaseModel):
    id: uuid.UUID
    source: str
    external_id: str | None = None
    date: datetime.date | None = None
    description: str | None = None
    total_amount: Decimal | None = None
    receipt_file_path: str | None = None
    url: str | None = None
    status: str
    is_marked_imported: bool
    ledger_transaction_id: uuid.UUID | None = None
    created_at: datetime.datetime
    allocations: list[StagedAllocationResponse] = []
    is_ready: bool
    supports_mark_imported: bool
    mark_imported_error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedStagedTransactionsResponse(BaseModel):
    items: list[StagedTransactionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class StagingAcceptRequest(BaseModel):
    staged_transaction_ids: list[uuid.UUID] | None = None


class StagingAcceptResponse(BaseModel):
    accepted_count: int
    ledger_transaction_ids: list[uuid.UUID]
    marked_imported_count: int
    mark_imported_errors: list[str]


class StagedBulkAllocateRequest(BaseModel):
    staged_transaction_ids: list[uuid.UUID]
    is_personal: bool = False
    company_id: uuid.UUID | None = None
    clear: bool = False

    @model_validator(mode="after")
    def validate_entity_choice(self) -> Self:
        if self.clear:
            if self.is_personal or self.company_id is not None:
                raise ValueError("Cannot specify is_personal or company_id when clear is True")
            return self
        if self.is_personal and self.company_id is not None:
            raise ValueError("Cannot specify both is_personal and company_id")
        if not self.is_personal and self.company_id is None:
            raise ValueError("Must specify either is_personal=True, a company_id, or clear=True")
        return self


class StagedBulkAllocateResponse(BaseModel):
    updated_count: int
    staged_transaction_ids: list[uuid.UUID]


class StagedBulkDismissRequest(BaseModel):
    staged_transaction_ids: list[uuid.UUID]


class StagedBulkDismissResponse(BaseModel):
    dismissed_count: int
    staged_transaction_ids: list[uuid.UUID]
    marked_imported_count: int
    mark_imported_errors: list[str]


def compute_staged_is_ready(staged_tx: StagedTransaction) -> bool:
    """Return True if the staged transaction has status STAGED, all metadata fields filled, and valid balanced allocations."""
    if staged_tx.status != "STAGED":
        return False

    if staged_tx.date is None or staged_tx.description is None or staged_tx.total_amount is None:
        return False

    allocs = staged_tx.allocations
    if not allocs:
        return False

    total = Decimal(str(staged_tx.total_amount)).quantize(Decimal("0.01"))
    alloc_sum = sum((Decimal(str(a.amount)).quantize(Decimal("0.01")) for a in allocs), Decimal("0.00"))
    if alloc_sum != total:
        return False

    if len(allocs) > 1:
        for a in allocs:
            if a.is_personal or a.company_id is None:
                return False
        return True

    single = allocs[0]
    if single.is_personal:
        return single.company_id is None
    return single.company_id is not None


def serialize_staged_transaction(
    staged_tx: StagedTransaction,
    mark_imported_error: str | None = None,
) -> StagedTransactionResponse:
    """Convert a StagedTransaction ORM model into a StagedTransactionResponse."""
    importer = get_importer_by_source(staged_tx.source)
    supports_mark = importer.supports_mark_imported if importer is not None else False
    return StagedTransactionResponse(
        id=staged_tx.id,
        source=staged_tx.source,
        external_id=staged_tx.external_id,
        date=staged_tx.date,
        description=staged_tx.description,
        total_amount=staged_tx.total_amount,
        receipt_file_path=staged_tx.receipt_file_path,
        url=staged_tx.url,
        status=staged_tx.status,
        is_marked_imported=staged_tx.is_marked_imported,
        ledger_transaction_id=staged_tx.ledger_transaction_id,
        created_at=staged_tx.created_at,
        allocations=[StagedAllocationResponse.model_validate(a) for a in staged_tx.allocations],
        is_ready=compute_staged_is_ready(staged_tx),
        supports_mark_imported=supports_mark,
        mark_imported_error=mark_imported_error,
    )
