import datetime
import json
import math
import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models.allocation import Allocation
from models.company import Company
from models.transaction import Transaction
from schemas.allocation import (
    AllocationItem,
    AllocationResponse,
    AllocationUpdateRequest,
    LockUpdateRequest,
)
from schemas.transaction import (
    PaginatedTransactionsResponse,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from services.receipts import delete_receipt_file, save_receipt_file

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=PaginatedTransactionsResponse)
def list_transactions(
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    rowsPerPage: Annotated[int | None, Query(ge=1, le=100, description="Alias for page_size")] = None,
    sort_by: Annotated[str, Query(description="Field to sort by")] = "date",
    sortBy: Annotated[str | None, Query(description="Alias for sort_by")] = None,
    descending: Annotated[bool, Query(description="Sort descending if true")] = True,
    order: Annotated[str | None, Query(description="'asc' or 'desc'")] = None,
    source: Annotated[str | None, Query(description="Filter by source")] = None,
    start_date: Annotated[datetime.date | None, Query(description="Filter by start date (inclusive)")] = None,
    end_date: Annotated[datetime.date | None, Query(description="Filter by end date (inclusive)")] = None,
    company_id: Annotated[uuid.UUID | None, Query(description="Filter by company ID")] = None,
) -> PaginatedTransactionsResponse:
    """Retrieve transactions with server-side pagination, sorting, and filtering."""
    effective_page_size = rowsPerPage if rowsPerPage is not None else page_size
    effective_sort_by = (sortBy if sortBy is not None else sort_by).lower()
    if order is not None:
        effective_descending = order.lower() == "desc"
    else:
        effective_descending = descending

    sort_field_map = {
        "date": Transaction.date,
        "total_amount": Transaction.total_amount,
        "description": Transaction.description,
        "source": Transaction.source,
        "id": Transaction.id,
    }
    column = sort_field_map.get(effective_sort_by, Transaction.date)
    sort_expr = column.desc() if effective_descending else column.asc()

    filters = []
    if source is not None:
        filters.append(Transaction.source == source)
    if start_date is not None:
        filters.append(Transaction.date >= start_date)
    if end_date is not None:
        filters.append(Transaction.date <= end_date)
    if company_id is not None:
        filters.append(Transaction.allocations.any(Allocation.company_id == company_id))

    count_stmt = select(func.count()).select_from(Transaction)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total_count = db.scalar(count_stmt) or 0
    total_pages = math.ceil(total_count / effective_page_size) if total_count > 0 else 0

    stmt = select(Transaction).options(selectinload(Transaction.allocations))
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(sort_expr, Transaction.id.desc()).offset((page - 1) * effective_page_size).limit(effective_page_size)
    items = list(db.scalars(stmt).all())

    return PaginatedTransactionsResponse(
        items=items,
        total=total_count,
        page=page,
        page_size=effective_page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Transaction:
    """Create a manual transaction, optionally with an uploaded receipt file and split allocations."""
    content_type = request.headers.get("content-type", "")
    uploaded_file: UploadFile | None = None

    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            for _, val in form.items():
                if hasattr(val, "filename") and getattr(val, "filename", None):
                    uploaded_file = val  # type: ignore[assignment]
                    break

            clean_dict: dict[str, object] = {}
            for k, v in form.items():
                if hasattr(v, "filename"):
                    continue
                if isinstance(v, str) and k in ("external_id", "receipt_file_path", "company_id") and not v.strip():
                    clean_dict[k] = None
                elif isinstance(v, str) and k == "allocations":
                    if not v.strip():
                        clean_dict[k] = None
                    else:
                        try:
                            clean_dict[k] = json.loads(v)
                        except Exception:
                            clean_dict[k] = v
                else:
                    clean_dict[k] = v
            payload = TransactionCreate(**clean_dict)
        else:
            body = await request.json()
            payload = TransactionCreate(**body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    alloc_list = payload.allocations or []

    # Split balance & allocation validation
    split_sum = sum((alloc.amount for alloc in alloc_list), Decimal("0"))
    if split_sum != payload.total_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sum of split allocations ({split_sum}) does not equal transaction total amount ({payload.total_amount})",
        )
    for alloc_item in alloc_list:
        if alloc_item.is_personal:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manual transaction allocations must be business allocations (is_personal=False)",
            )
        target_company = db.get(Company, alloc_item.company_id)
        if target_company is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Company with ID '{alloc_item.company_id}' not found",
            )

    if payload.external_id is not None:
        existing = db.scalar(
            select(Transaction).where(
                Transaction.source == payload.source,
                Transaction.external_id == payload.external_id,
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Transaction with source '{payload.source}' and external_id '{payload.external_id}' already exists",
            )

    tx_id = uuid.uuid4()
    receipt_path = payload.receipt_file_path
    if uploaded_file is not None:
        receipt_path = await save_receipt_file(uploaded_file, tx_id)

    transaction = Transaction(
        id=tx_id,
        source=payload.source,
        external_id=payload.external_id,
        date=payload.date,
        description=payload.description,
        total_amount=payload.total_amount,
        currency_code=payload.currency_code,
        receipt_file_path=receipt_path,
    )

    for alloc_item in alloc_list:
        alloc = Allocation(
            id=alloc_item.id or uuid.uuid4(),
            transaction_id=tx_id,
            amount=alloc_item.amount,
            is_personal=False,
            company_id=alloc_item.company_id,
            is_locked=False,
        )
        transaction.allocations.append(alloc)

    db.add(transaction)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transaction duplicate constraint violation",
        ) from exc

    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == tx_id)
    created_tx = db.scalar(stmt)
    return created_tx if created_tx is not None else transaction


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Transaction:
    """Retrieve a single transaction by ID with its allocations."""
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )
    return transaction


def _allocations_match_existing(items: list[AllocationItem] | None, existing: list[Allocation]) -> bool:
    if items is None or len(items) != len(existing):
        return False
    existing_by_id = {a.id: a for a in existing}
    seen_ids: set[uuid.UUID] = set()
    for item in items:
        if item.id is None or item.id not in existing_by_id or item.id in seen_ids:
            return False
        seen_ids.add(item.id)
        ex = existing_by_id[item.id]
        effective_company_id = None if item.is_personal else item.company_id
        if item.amount != ex.amount or item.is_personal != ex.is_personal or effective_company_id != ex.company_id or item.is_locked != ex.is_locked:
            return False
    return True


def _validate_and_apply_allocations(
    transaction: Transaction,
    items: list[AllocationItem],
    effective_total_amount: Decimal,
    db: Session,
) -> None:
    existing_allocations = list(transaction.allocations)
    is_fully_locked = len(existing_allocations) > 0 and all(a.is_locked for a in existing_allocations)
    if is_fully_locked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify transaction: all allocations are locked",
        )

    existing_locked = [a for a in existing_allocations if a.is_locked]
    if existing_locked:
        matched_ids: set[uuid.UUID] = set()
        for locked_alloc in existing_locked:
            matches = [item for item in items if item.id == locked_alloc.id]
            if len(matches) != 1 or locked_alloc.id in matched_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot modify or remove locked allocations without unlocking them first",
                )
            matched_ids.add(locked_alloc.id)
            match = matches[0]
            effective_comp_id = None if match.is_personal else match.company_id
            if (
                match.amount != locked_alloc.amount
                or match.is_personal != locked_alloc.is_personal
                or effective_comp_id != locked_alloc.company_id
                or not match.is_locked
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot modify or remove locked allocations without unlocking them first",
                )

    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one allocation is required",
        )

    if len(items) > 1 and any(item.is_personal for item in items):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only business transactions can be split. Remove extra splits before marking as personal.",
        )

    for item in items:
        if item.is_personal:
            item.company_id = None
        else:
            if item.company_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Business allocation requires a valid company_id",
                )
            company = db.get(Company, item.company_id)
            if company is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Company with ID '{item.company_id}' not found",
                )

    split_sum = sum((item.amount for item in items), Decimal("0"))
    if split_sum != effective_total_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sum of split allocations ({split_sum}) does not equal transaction total amount ({effective_total_amount})",
        )

    transaction.allocations.clear()
    db.flush()

    for item in items:
        alloc = Allocation(
            id=item.id or uuid.uuid4(),
            transaction_id=transaction.id,
            amount=item.amount,
            is_personal=item.is_personal,
            company_id=None if item.is_personal else item.company_id,
            is_locked=item.is_locked,
        )
        transaction.allocations.append(alloc)


@router.put("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Transaction:
    """Unified update for transaction metadata, split allocations, and optional receipt replacement/removal."""
    content_type = request.headers.get("content-type", "")
    uploaded_file: UploadFile | None = None

    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            for _, val in form.items():
                if hasattr(val, "filename") and getattr(val, "filename", None):
                    uploaded_file = val  # type: ignore[assignment]
                    break

            clean_dict: dict[str, object] = {}
            for k, v in form.items():
                if hasattr(v, "filename"):
                    continue
                if isinstance(v, str) and k in ("external_id", "receipt_file_path") and not v.strip():
                    clean_dict[k] = None
                elif isinstance(v, str) and k == "allocations":
                    if not v.strip():
                        clean_dict[k] = None
                    else:
                        try:
                            clean_dict[k] = json.loads(v)
                        except Exception:
                            clean_dict[k] = v
                else:
                    clean_dict[k] = v
            payload = TransactionUpdate(**clean_dict)
        else:
            body = await request.json()
            payload = TransactionUpdate(**body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    existing_allocations = list(transaction.allocations)
    is_fully_locked = len(existing_allocations) > 0 and all(a.is_locked for a in existing_allocations)
    has_locked_allocations = any(a.is_locked for a in existing_allocations)
    update_data = payload.model_dump(exclude_unset=True)
    is_receipt_only_op = uploaded_file is not None or payload.remove_receipt

    date_modified = "date" in update_data and (payload.date != transaction.date or not is_receipt_only_op)
    desc_modified = "description" in update_data and (payload.description != transaction.description or not is_receipt_only_op)
    amount_modified = "total_amount" in update_data and (payload.total_amount != transaction.total_amount or not is_receipt_only_op)
    allocs_modified = "allocations" in update_data and (not _allocations_match_existing(payload.allocations, existing_allocations) or not is_receipt_only_op)

    if is_fully_locked and (date_modified or desc_modified or amount_modified or allocs_modified):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify transaction: all allocations are locked",
        )

    if has_locked_allocations and (date_modified or desc_modified):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify transaction date or description while allocations are locked",
        )

    new_source = update_data.get("source", transaction.source)
    new_external_id = update_data.get("external_id", transaction.external_id)
    if new_external_id is not None and (new_source != transaction.source or new_external_id != transaction.external_id):
        dup = db.scalar(
            select(Transaction).where(
                Transaction.source == new_source,
                Transaction.external_id == new_external_id,
                Transaction.id != transaction_id,
            )
        )
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Transaction with source '{new_source}' and external_id '{new_external_id}' already exists",
            )

    effective_total_amount = payload.total_amount if payload.total_amount is not None else transaction.total_amount

    if not is_fully_locked:
        if "allocations" in update_data and payload.allocations is not None:
            _validate_and_apply_allocations(transaction, payload.allocations, effective_total_amount, db)
        elif "total_amount" in update_data and len(existing_allocations) > 0:
            existing_sum = sum((a.amount for a in existing_allocations), Decimal("0"))
            if existing_sum != effective_total_amount:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Sum of split allocations ({existing_sum}) does not equal transaction total amount ({effective_total_amount})",
                )

        scalar_fields = ("date", "description", "total_amount", "currency_code", "source", "external_id", "receipt_file_path")
        for key in scalar_fields:
            if key in update_data and getattr(payload, key) is not None or key == "external_id" and "external_id" in update_data:
                setattr(transaction, key, getattr(payload, key))

    if uploaded_file is not None:
        old_path = transaction.receipt_file_path
        saved_path = await save_receipt_file(uploaded_file, transaction.id)
        if old_path and old_path != saved_path:
            delete_receipt_file(old_path)
        transaction.receipt_file_path = saved_path
    elif payload.remove_receipt:
        if transaction.receipt_file_path:
            delete_receipt_file(transaction.receipt_file_path)
            transaction.receipt_file_path = None

    db.add(transaction)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transaction duplicate constraint violation",
        ) from exc

    db.refresh(transaction)
    return transaction


@router.put("/{transaction_id}/allocations", response_model=list[AllocationResponse])
def update_transaction_allocations(
    transaction_id: uuid.UUID,
    payload: list[AllocationItem] | AllocationUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> list[Allocation]:
    """Replace split allocations for a transaction with partial/full lock and personal/business split validation."""
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    items = payload if isinstance(payload, list) else payload.allocations
    _validate_and_apply_allocations(transaction, items, transaction.total_amount, db)

    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction.allocations


@router.post("/{transaction_id}/receipt", response_model=TransactionResponse)
async def upload_transaction_receipt(
    transaction_id: uuid.UUID,
    file: UploadFile,
    db: Annotated[Session, Depends(get_db)],
) -> Transaction:
    """Upload or replace a receipt file and attach it to the transaction."""
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    old_path = transaction.receipt_file_path
    saved_path = await save_receipt_file(file, transaction.id)
    if old_path and old_path != saved_path:
        delete_receipt_file(old_path)
    transaction.receipt_file_path = saved_path
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.delete("/{transaction_id}/receipt", response_model=TransactionResponse)
def delete_transaction_receipt(
    transaction_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Transaction:
    """Remove an attached receipt from a transaction and delete the file from disk."""
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    if transaction.receipt_file_path:
        delete_receipt_file(transaction.receipt_file_path)
        transaction.receipt_file_path = None
        db.add(transaction)
        db.commit()
        db.refresh(transaction)

    return transaction


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Delete a transaction, its allocations, and its receipt file if no allocations are locked."""
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    for alloc in transaction.allocations:
        if alloc.is_locked:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete transaction: transaction contains locked allocations",
            )

    receipt_path = transaction.receipt_file_path
    db.delete(transaction)
    db.commit()
    if receipt_path:
        delete_receipt_file(receipt_path)


@router.put("/{transaction_id}/lock", response_model=TransactionResponse)
def update_transaction_lock(
    transaction_id: uuid.UUID,
    payload: LockUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Transaction:
    """Lock or unlock all allocations belonging to a transaction."""
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    for alloc in transaction.allocations:
        alloc.is_locked = payload.is_locked
        db.add(alloc)

    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction
