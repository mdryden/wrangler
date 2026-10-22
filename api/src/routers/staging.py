import json
import math
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from core.config import settings
from database import get_db
from models.allocation import Allocation
from models.company import Company
from models.staged_allocation import StagedAllocation
from models.staged_transaction import StagedTransaction
from models.transaction import Transaction
from schemas.staging import (
    PaginatedStagedTransactionsResponse,
    StagedAllocationItem,
    StagedBulkAllocateRequest,
    StagedBulkAllocateResponse,
    StagedBulkDismissRequest,
    StagedBulkDismissResponse,
    StagedTransactionResponse,
    StagedTransactionUpdate,
    StagingAcceptRequest,
    StagingAcceptResponse,
    compute_staged_is_ready,
    serialize_staged_transaction,
)
from services.ai.base import ReceiptParseResult
from services.ai.factory import get_receipt_parser
from services.importers.registry import format_personal_fallback_description, get_importer_by_source
from services.receipts import delete_receipt_file, get_receipt_file_path, save_receipt_file

from .receipts import EXTENSION_TO_MIME

router = APIRouter(prefix="/api/staging", tags=["staging"])


def _get_staged_tx_or_404(db: Session, staged_id: uuid.UUID) -> StagedTransaction:
    stmt = select(StagedTransaction).options(selectinload(StagedTransaction.allocations)).where(StagedTransaction.id == staged_id)
    staged_tx = db.scalar(stmt)
    if staged_tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staged transaction with ID '{staged_id}' not found",
        )
    return staged_tx


def _validate_and_apply_staged_allocations(
    staged_tx: StagedTransaction,
    items: list[StagedAllocationItem],
    effective_total_amount: Decimal,
    db: Session,
) -> None:
    if not items:
        staged_tx.allocations.clear()
        db.flush()
        return

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

    split_sum = sum((Decimal(str(item.amount)).quantize(Decimal("0.01")) for item in items), Decimal("0.00"))
    target_total = Decimal(str(effective_total_amount)).quantize(Decimal("0.01"))
    if split_sum != target_total:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sum of split allocations ({split_sum}) does not equal staged transaction total amount ({target_total})",
        )

    staged_tx.allocations.clear()
    db.flush()

    for item in items:
        s_alloc = StagedAllocation(
            id=item.id or uuid.uuid4(),
            staged_transaction_id=staged_tx.id,
            amount=item.amount,
            is_personal=item.is_personal,
            company_id=None if item.is_personal else item.company_id,
        )
        staged_tx.allocations.append(s_alloc)


@router.get("", response_model=PaginatedStagedTransactionsResponse)
def list_staged_transactions(
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status", description="Filter by status")] = "STAGED",
    source: Annotated[str | None, Query(description="Filter by source")] = None,
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 50,
) -> PaginatedStagedTransactionsResponse:
    """Retrieve staged transactions with pagination and filtering by status and source."""
    filters = []
    if status_filter is not None and status_filter.strip():
        filters.append(StagedTransaction.status == status_filter.strip().upper())
    if source is not None and source.strip():
        filters.append(StagedTransaction.source == source.strip())

    count_stmt = select(func.count()).select_from(StagedTransaction)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total_count = db.scalar(count_stmt) or 0
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

    stmt = select(StagedTransaction).options(selectinload(StagedTransaction.allocations))
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(StagedTransaction.date.desc().nullslast(), StagedTransaction.id.desc()).offset((page - 1) * page_size).limit(page_size)
    items = list(db.scalars(stmt).all())

    return PaginatedStagedTransactionsResponse(
        items=[serialize_staged_transaction(stx) for stx in items],
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.put("/{staged_id}", response_model=StagedTransactionResponse)
async def update_staged_transaction(
    staged_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> StagedTransactionResponse:
    """Update a STAGED transaction's metadata, draft allocations, and/or receipt."""
    content_type = request.headers.get("content-type", "")
    uploaded_file: UploadFile | None = None

    try:
        if "multipart/form-data" in content_type.lower():
            form = await request.form()
            for _, val in form.items():
                if hasattr(val, "filename") and getattr(val, "filename", None):
                    uploaded_file = val  # type: ignore[assignment]
                    break

            clean_dict: dict[str, object] = {}
            for k, v in form.items():
                if hasattr(v, "filename"):
                    continue
                if isinstance(v, str) and k == "allocations":
                    if not v.strip():
                        clean_dict[k] = None
                    else:
                        try:
                            clean_dict[k] = json.loads(v)
                        except Exception:
                            clean_dict[k] = v
                else:
                    clean_dict[k] = v
            payload = StagedTransactionUpdate(**clean_dict)
        else:
            body = await request.json()
            payload = StagedTransactionUpdate(**body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    staged_tx = _get_staged_tx_or_404(db, staged_id)
    if staged_tx.status != "STAGED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot modify staged transaction with status '{staged_tx.status}'",
        )

    update_data = payload.model_dump(exclude_unset=True)
    effective_total_amount = payload.total_amount if payload.total_amount is not None else staged_tx.total_amount

    if "allocations" in update_data and payload.allocations is not None:
        if effective_total_amount is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot allocate staged transaction without a total amount",
            )
        _validate_and_apply_staged_allocations(staged_tx, payload.allocations, effective_total_amount, db)
    elif "total_amount" in update_data and len(staged_tx.allocations) > 0:
        if effective_total_amount is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot set total amount to null when allocations exist",
            )
        existing_sum = sum((Decimal(str(a.amount)).quantize(Decimal("0.01")) for a in staged_tx.allocations), Decimal("0.00"))
        target_total = Decimal(str(effective_total_amount)).quantize(Decimal("0.01"))
        if existing_sum != target_total:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sum of split allocations ({existing_sum}) does not equal staged transaction total amount ({target_total})",
            )

    for key in ("date", "description", "total_amount"):
        if key in update_data and getattr(payload, key) is not None:
            setattr(staged_tx, key, getattr(payload, key))

    if "url" in update_data:
        staged_tx.url = payload.url.strip() if payload.url else None

    if uploaded_file is not None:
        old_path = staged_tx.receipt_file_path
        saved_path = await save_receipt_file(uploaded_file, staged_tx.id)
        if old_path and old_path != saved_path:
            delete_receipt_file(old_path)
        staged_tx.receipt_file_path = saved_path
    elif payload.remove_receipt:
        if staged_tx.receipt_file_path:
            delete_receipt_file(staged_tx.receipt_file_path)
            staged_tx.receipt_file_path = None

    db.add(staged_tx)
    db.commit()
    db.refresh(staged_tx)
    return serialize_staged_transaction(staged_tx)


@router.post("/{staged_id}/receipt", response_model=StagedTransactionResponse)
async def upload_staged_receipt(
    staged_id: uuid.UUID,
    file: UploadFile,
    db: Annotated[Session, Depends(get_db)],
) -> StagedTransactionResponse:
    """Upload or replace a receipt file on a STAGED transaction."""
    staged_tx = _get_staged_tx_or_404(db, staged_id)
    if staged_tx.status != "STAGED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot upload receipt for staged transaction with status '{staged_tx.status}'",
        )

    old_path = staged_tx.receipt_file_path
    saved_path = await save_receipt_file(file, staged_tx.id)
    if old_path and old_path != saved_path:
        delete_receipt_file(old_path)
    staged_tx.receipt_file_path = saved_path
    db.add(staged_tx)
    db.commit()
    db.refresh(staged_tx)
    return serialize_staged_transaction(staged_tx)


@router.delete("/{staged_id}/receipt", response_model=StagedTransactionResponse)
def delete_staged_receipt(
    staged_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> StagedTransactionResponse:
    """Remove a receipt file from a STAGED transaction and delete it from disk."""
    staged_tx = _get_staged_tx_or_404(db, staged_id)
    if staged_tx.status != "STAGED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete receipt for staged transaction with status '{staged_tx.status}'",
        )

    if staged_tx.receipt_file_path:
        delete_receipt_file(staged_tx.receipt_file_path)
        staged_tx.receipt_file_path = None
        db.add(staged_tx)
        db.commit()
        db.refresh(staged_tx)

    return serialize_staged_transaction(staged_tx)


@router.post("/{staged_id}/parse-receipt", response_model=ReceiptParseResult)
async def parse_staged_receipt(
    staged_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ReceiptParseResult:
    """Parse an existing receipt on disk associated with a staged transaction."""
    staged_tx = _get_staged_tx_or_404(db, staged_id)

    if staged_tx.status != "STAGED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot parse receipt for staged transaction with status '{staged_tx.status}'",
        )

    if not staged_tx.receipt_file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No receipt attached to staged transaction",
        )

    try:
        path = get_receipt_file_path(staged_tx.receipt_file_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        file_bytes = path.read_bytes()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if len(file_bytes) > settings.MAX_RECEIPT_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Receipt file exceeds 20MB limit",
        )

    ext = path.suffix.lower()
    if ext not in EXTENSION_TO_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Allowed: .jpg, .jpeg, .png, .webp, .pdf",
        )
    mime_type = EXTENSION_TO_MIME[ext]

    try:
        parser = get_receipt_parser()
        return await parser.parse_receipt(
            file_bytes=file_bytes,
            filename=path.name,
            mime_type=mime_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/{staged_id}/dismiss", response_model=StagedTransactionResponse)
async def dismiss_staged_transaction(
    staged_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> StagedTransactionResponse:
    """Dismiss a STAGED transaction, clear allocations and unaccepted receipt, and invoke mark_as_imported if supported."""
    staged_tx = _get_staged_tx_or_404(db, staged_id)
    if staged_tx.status != "STAGED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot dismiss staged transaction with status '{staged_tx.status}'",
        )

    staged_tx.allocations.clear()
    if staged_tx.receipt_file_path:
        delete_receipt_file(staged_tx.receipt_file_path)
        staged_tx.receipt_file_path = None
    staged_tx.status = "DISMISSED"
    db.add(staged_tx)
    db.commit()
    db.refresh(staged_tx)

    mark_error: str | None = None
    importer = get_importer_by_source(staged_tx.source)
    if importer is not None and importer.supports_mark_imported and staged_tx.external_id is not None and not staged_tx.is_marked_imported:
        try:
            await importer.mark_as_imported([staged_tx.external_id])
            staged_tx.is_marked_imported = True
            db.add(staged_tx)
            db.commit()
            db.refresh(staged_tx)
        except Exception as exc:
            mark_error = str(exc)

    return serialize_staged_transaction(staged_tx, mark_imported_error=mark_error)


@router.post("/{staged_id}/restore", response_model=StagedTransactionResponse)
def restore_staged_transaction(
    staged_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> StagedTransactionResponse:
    """Restore a DISMISSED transaction back to STAGED status."""
    staged_tx = _get_staged_tx_or_404(db, staged_id)
    if staged_tx.status != "DISMISSED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot restore staged transaction with status '{staged_tx.status}'",
        )

    staged_tx.allocations.clear()
    staged_tx.status = "STAGED"
    db.add(staged_tx)
    db.commit()
    db.refresh(staged_tx)
    return serialize_staged_transaction(staged_tx)


@router.post("/bulk-allocate", response_model=StagedBulkAllocateResponse)
def bulk_allocate_staged(
    payload: StagedBulkAllocateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> StagedBulkAllocateResponse:
    """Atomically update allocations for a batch of staged transactions to 100% of an entity or clear allocations."""
    if not payload.staged_transaction_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="staged_transaction_ids must not be empty",
        )

    if payload.company_id is not None:
        company = db.get(Company, payload.company_id)
        if company is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Company not found",
            )

    stmt = (
        select(StagedTransaction)
        .options(selectinload(StagedTransaction.allocations))
        .where(StagedTransaction.id.in_(payload.staged_transaction_ids))
        .order_by(StagedTransaction.date.asc(), StagedTransaction.id.asc())
    )
    records = list(db.scalars(stmt).all())
    qualifying_staged = [stx for stx in records if stx.status == "STAGED"]

    for staged_tx in qualifying_staged:
        staged_tx.allocations.clear()
        if not payload.clear:
            if staged_tx.total_amount is None or staged_tx.total_amount == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot allocate staged transaction without a total amount",
                )
            new_alloc = StagedAllocation(
                id=uuid.uuid4(),
                staged_transaction_id=staged_tx.id,
                amount=staged_tx.total_amount,
                is_personal=payload.is_personal,
                company_id=payload.company_id,
            )
            staged_tx.allocations.append(new_alloc)

    db.commit()

    return StagedBulkAllocateResponse(
        updated_count=len(qualifying_staged),
        staged_transaction_ids=[stx.id for stx in qualifying_staged],
    )


@router.post("/bulk-dismiss", response_model=StagedBulkDismissResponse)
async def bulk_dismiss_staged(
    payload: StagedBulkDismissRequest,
    db: Annotated[Session, Depends(get_db)],
) -> StagedBulkDismissResponse:
    """Atomically dismiss a batch of staged transactions, clean receipts, and trigger importer mark_as_imported hooks."""
    if not payload.staged_transaction_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="staged_transaction_ids must not be empty",
        )

    stmt = (
        select(StagedTransaction)
        .options(selectinload(StagedTransaction.allocations))
        .where(StagedTransaction.id.in_(payload.staged_transaction_ids))
        .order_by(StagedTransaction.date.asc(), StagedTransaction.id.asc())
    )
    records = list(db.scalars(stmt).all())
    qualifying_staged = [stx for stx in records if stx.status == "STAGED"]

    for staged_tx in qualifying_staged:
        staged_tx.allocations.clear()
        if staged_tx.receipt_file_path:
            delete_receipt_file(staged_tx.receipt_file_path)
            staged_tx.receipt_file_path = None
        staged_tx.status = "DISMISSED"
        db.add(staged_tx)

    db.commit()

    by_source: dict[str, list[StagedTransaction]] = defaultdict(list)
    for stx in qualifying_staged:
        if stx.external_id is not None and not stx.is_marked_imported:
            by_source[stx.source].append(stx)

    marked_imported_count = 0
    mark_imported_errors: list[str] = []

    for source_name, staged_rows in by_source.items():
        importer = get_importer_by_source(source_name)
        if importer is not None and importer.supports_mark_imported:
            ext_ids = [row.external_id for row in staged_rows if row.external_id is not None]
            try:
                await importer.mark_as_imported(ext_ids)
                for row in staged_rows:
                    row.is_marked_imported = True
                    db.add(row)
                db.commit()
                marked_imported_count += len(staged_rows)
            except Exception as exc:
                db.rollback()
                mark_imported_errors.append(f"{source_name}: {exc}")

    return StagedBulkDismissResponse(
        dismissed_count=len(qualifying_staged),
        staged_transaction_ids=[stx.id for stx in qualifying_staged],
        marked_imported_count=marked_imported_count,
        mark_imported_errors=mark_imported_errors,
    )


@router.post("/accept", response_model=StagingAcceptResponse)
async def accept_staged_transactions(
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[StagingAcceptRequest | None, Body()] = None,
) -> StagingAcceptResponse:
    """Accept ready STAGED transactions into the Ledger atomically and invoke mark_as_imported hooks."""
    requested_ids = payload.staged_transaction_ids if payload is not None else None

    if requested_ids is not None:
        if not requested_ids:
            return StagingAcceptResponse(
                accepted_count=0,
                ledger_transaction_ids=[],
                marked_imported_count=0,
                mark_imported_errors=[],
            )
        stmt = (
            select(StagedTransaction)
            .options(selectinload(StagedTransaction.allocations))
            .where(StagedTransaction.id.in_(requested_ids))
            .order_by(StagedTransaction.date.asc(), StagedTransaction.id.asc())
        )
        found = list(db.scalars(stmt).all())
        found_by_id = {stx.id: stx for stx in found}
        for req_id in requested_ids:
            if req_id not in found_by_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Staged transaction with ID '{req_id}' not found",
                )
        for stx in found:
            if stx.status != "STAGED":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Staged transaction '{stx.id}' is not in STAGED status (current: '{stx.status}')",
                )
            if not compute_staged_is_ready(stx):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Staged transaction '{stx.id}' ('{stx.description}') is not ready for acceptance",
                )
        target_staged = found
    else:
        stmt = (
            select(StagedTransaction)
            .options(selectinload(StagedTransaction.allocations))
            .where(StagedTransaction.status == "STAGED")
            .order_by(StagedTransaction.date.asc(), StagedTransaction.id.asc())
        )
        all_staged = list(db.scalars(stmt).all())
        target_staged = [stx for stx in all_staged if compute_staged_is_ready(stx)]

    if not target_staged:
        return StagingAcceptResponse(
            accepted_count=0,
            ledger_transaction_ids=[],
            marked_imported_count=0,
            mark_imported_errors=[],
        )

    ledger_tx_ids: list[uuid.UUID] = []
    staged_to_tx_id: list[tuple[StagedTransaction, uuid.UUID]] = []
    for stx in target_staged:
        tx_id = uuid.uuid4()
        resolved_description = (stx.description or "").strip()
        if not resolved_description:
            is_personal = len(stx.allocations) == 1 and stx.allocations[0].is_personal
            if is_personal:
                resolved_description = format_personal_fallback_description(stx.source)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Staged transaction '{stx.id}' is missing a description",
                )

        ledger_tx = Transaction(
            id=tx_id,
            source=stx.source,
            external_id=stx.external_id,
            date=stx.date,
            description=resolved_description,
            total_amount=stx.total_amount,
            receipt_file_path=stx.receipt_file_path,
            url=stx.url,
        )
        for s_alloc in stx.allocations:
            ledger_tx.allocations.append(
                Allocation(
                    id=uuid.uuid4(),
                    transaction_id=tx_id,
                    amount=s_alloc.amount,
                    is_personal=s_alloc.is_personal,
                    company_id=None if s_alloc.is_personal else s_alloc.company_id,
                    is_locked=False,
                )
            )
        db.add(ledger_tx)
        staged_to_tx_id.append((stx, tx_id))
        ledger_tx_ids.append(tx_id)

    db.flush()

    for stx, tx_id in staged_to_tx_id:
        stx.status = "ACCEPTED"
        stx.ledger_transaction_id = tx_id
        db.add(stx)

    db.commit()

    # Group accepted records with non-null external_id and is_marked_imported == False by source
    by_source: dict[str, list[StagedTransaction]] = defaultdict(list)
    for stx in target_staged:
        if stx.external_id is not None and not stx.is_marked_imported:
            by_source[stx.source].append(stx)

    marked_imported_count = 0
    mark_imported_errors: list[str] = []

    for source_name, staged_rows in by_source.items():
        importer = get_importer_by_source(source_name)
        ext_ids = [row.external_id for row in staged_rows if row.external_id is not None]
        try:
            if importer is not None:
                await importer.mark_as_imported(ext_ids)
            for row in staged_rows:
                row.is_marked_imported = True
                db.add(row)
            db.commit()
            if importer is not None and importer.supports_mark_imported:
                marked_imported_count += len(staged_rows)
        except Exception as exc:
            db.rollback()
            mark_imported_errors.append(f"{source_name}: {exc}")

    return StagingAcceptResponse(
        accepted_count=len(target_staged),
        ledger_transaction_ids=ledger_tx_ids,
        marked_imported_count=marked_imported_count,
        mark_imported_errors=mark_imported_errors,
    )
