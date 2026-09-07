import datetime
import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models.allocation import Allocation, SyncStatus
from models.company import Company
from models.transaction import Transaction
from schemas.allocation import AllocationItem, AllocationResponse, AllocationUpdateRequest
from schemas.transaction import (
    PaginatedTransactionsResponse,
    TransactionApproveRequest,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from services.receipts import save_receipt_file

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
    is_approved: Annotated[bool | None, Query(description="Filter by approval status")] = None,
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
        "is_approved": Transaction.is_approved,
        "id": Transaction.id,
    }
    column = sort_field_map.get(effective_sort_by, Transaction.date)
    sort_expr = column.desc() if effective_descending else column.asc()

    filters = []
    if source is not None:
        filters.append(Transaction.source == source)
    if is_approved is not None:
        filters.append(Transaction.is_approved == is_approved)
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
    """Create a manual transaction, optionally with an uploaded receipt file."""
    content_type = request.headers.get("content-type", "")
    uploaded_file: UploadFile | None = None

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
            elif isinstance(v, str) and k == "is_approved":
                clean_dict[k] = v.lower() in ("true", "1", "yes")
            else:
                clean_dict[k] = v
        payload = TransactionCreate(**clean_dict)
    else:
        body = await request.json()
        payload = TransactionCreate(**body)

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
        is_approved=payload.is_approved,
    )

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


@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> Transaction:
    """Update transaction metadata. Fails if any allocation is SYNCED."""
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    for alloc in transaction.allocations:
        if alloc.sync_status == SyncStatus.SYNCED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot modify transaction: transaction contains SYNCED allocations",
            )

    update_data = payload.model_dump(exclude_unset=True)

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

    for key, val in update_data.items():
        setattr(transaction, key, val)

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


@router.put("/{transaction_id}/approve", response_model=TransactionResponse)
def approve_transaction(
    transaction_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: TransactionApproveRequest | None = None,
) -> Transaction:
    """Toggle or explicitly set transaction approval status."""
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    if payload is not None and payload.is_approved is not None:
        transaction.is_approved = payload.is_approved
    else:
        transaction.is_approved = not transaction.is_approved

    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.put("/{transaction_id}/allocations", response_model=list[AllocationResponse])
def update_transaction_allocations(
    transaction_id: uuid.UUID,
    payload: list[AllocationItem] | AllocationUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> list[Allocation]:
    """Replace split allocations for a transaction. Fails if any existing allocation is SYNCED."""
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    # Immutability validation: HTTP 400 if any existing allocation is SYNCED
    for alloc in transaction.allocations:
        if alloc.sync_status == SyncStatus.SYNCED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot modify allocations: transaction contains SYNCED allocations",
            )

    items = payload if isinstance(payload, list) else payload.allocations

    # Foreign key validation for companies
    for item in items:
        if not item.is_personal:
            if item.company_id is not None:
                company = db.get(Company, item.company_id)
                if company is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Company with ID '{item.company_id}' not found",
                    )

    # Clear and replace existing allocations
    transaction.allocations.clear()
    db.flush()

    for item in items:
        alloc = Allocation(
            id=item.id or uuid.uuid4(),
            transaction_id=transaction.id,
            amount=item.amount,
            is_personal=item.is_personal,
            company_id=None if item.is_personal else item.company_id,
            sync_status=item.sync_status,
        )
        transaction.allocations.append(alloc)

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
    """Upload a receipt file and attach it to the transaction."""
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    saved_path = await save_receipt_file(file, transaction.id)
    transaction.receipt_file_path = saved_path
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Delete a transaction and its allocations if not synced."""
    stmt = select(Transaction).options(selectinload(Transaction.allocations)).where(Transaction.id == transaction_id)
    transaction = db.scalar(stmt)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID '{transaction_id}' not found",
        )

    for alloc in transaction.allocations:
        if alloc.sync_status == SyncStatus.SYNCED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete transaction: transaction contains SYNCED allocations",
            )

    db.delete(transaction)
    db.commit()
