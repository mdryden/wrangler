import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from database import get_db
from models.staged_transaction import StagedTransaction
from models.transaction import Transaction
from schemas.importer import ImporterMetadataResponse, ImporterRunResponse
from schemas.staging import serialize_staged_transaction
from services.importers.base import ImporterInputType, ImporterValidationError
from services.importers.registry import get_importer, list_importers
from services.receipts import sanitize_filename

router = APIRouter(prefix="/api/importers", tags=["importers"])


@router.get("", response_model=list[ImporterMetadataResponse])
def get_registered_importers() -> list[ImporterMetadataResponse]:
    """Return metadata for all registered importers."""
    return [
        ImporterMetadataResponse(
            importer_id=imp.importer_id,
            source_name=imp.source_name,
            display_name=imp.display_name,
            description=imp.description,
            input_type=imp.input_type,
            accepted_file_types=imp.accepted_file_types,
            supports_mark_imported=imp.supports_mark_imported,
        )
        for imp in list_importers()
    ]


@router.post("/{importer_id}/run", response_model=ImporterRunResponse)
async def run_importer(
    importer_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ImporterRunResponse:
    """Execute an importer and persist deduplicated records into staging."""
    importer = get_importer(importer_id)
    if importer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Importer '{importer_id}' not found",
        )

    file_bytes: bytes | None = None
    filename: str | None = None

    if importer.input_type == ImporterInputType.FILE:
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File upload (multipart/form-data) is required for this importer",
            )
        form = await request.form()
        uploaded = form.get("file")
        if not isinstance(uploaded, UploadFile) and not (hasattr(uploaded, "read") and hasattr(uploaded, "filename")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File field 'file' is required for this importer",
            )
        file_bytes = await uploaded.read()
        filename = uploaded.filename

    try:
        parsed_items = await importer.fetch_and_parse(file_bytes=file_bytes, filename=filename)
    except ImporterValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    total_parsed = len(parsed_items)
    skipped_duplicates = 0
    new_staged_records: list[StagedTransaction] = []

    # Collect non-null external_ids to batch-check existing database records
    candidate_ext_ids = {item.external_id for item in parsed_items if item.external_id is not None}
    existing_ext_ids: set[str] = set()

    if candidate_ext_ids:
        staged_existing = db.scalars(
            select(StagedTransaction.external_id).where(
                StagedTransaction.source == importer.source_name,
                StagedTransaction.external_id.in_(candidate_ext_ids),
            )
        ).all()
        tx_existing = db.scalars(
            select(Transaction.external_id).where(
                Transaction.source == importer.source_name,
                Transaction.external_id.in_(candidate_ext_ids),
            )
        ).all()
        existing_ext_ids.update(ext_id for ext_id in staged_existing if ext_id is not None)
        existing_ext_ids.update(ext_id for ext_id in tx_existing if ext_id is not None)

    seen_external_ids: set[str] = set()

    for item in parsed_items:
        ext_id = item.external_id
        if ext_id is not None:
            if ext_id in seen_external_ids or ext_id in existing_ext_ids:
                skipped_duplicates += 1
                continue
            seen_external_ids.add(ext_id)

        staged_id = uuid.uuid4()
        receipt_file_path: str | None = None

        if item.receipt is not None:
            settings.RECEIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            safe_name = sanitize_filename(item.receipt.filename or "receipt.pdf")
            unique_filename = f"{staged_id}_{safe_name}"
            target_path = settings.RECEIPT_STORAGE_DIR / unique_filename
            target_path.write_bytes(item.receipt.content)
            receipt_file_path = unique_filename

        staged_tx = StagedTransaction(
            id=staged_id,
            source=importer.source_name,
            external_id=ext_id,
            date=item.date,
            description=item.description,
            total_amount=item.total_amount,
            currency_code=item.currency_code,
            receipt_file_path=receipt_file_path,
            status="STAGED",
            is_marked_imported=False,
        )
        db.add(staged_tx)
        new_staged_records.append(staged_tx)

    db.commit()
    for staged_tx in new_staged_records:
        db.refresh(staged_tx)

    return ImporterRunResponse(
        importer_id=importer.importer_id,
        total_parsed=total_parsed,
        staged_count=len(new_staged_records),
        skipped_duplicates=skipped_duplicates,
        items=[serialize_staged_transaction(stx) for stx in new_staged_records],
    )
