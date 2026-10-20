import asyncio
import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from database import get_db
from models.staged_transaction import StagedTransaction
from models.transaction import Transaction
from schemas.importer import ImporterMetadataResponse, ImporterRunResponse
from schemas.staging import serialize_staged_transaction
from services.importers.base import (
    ImportedTransactionData,
    ImporterInputType,
    ImporterValidationError,
)
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

    files_to_process: list[tuple[str, bytes]] = []

    if importer.input_type == ImporterInputType.FILE:
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File upload (multipart/form-data) is required for this importer",
            )
        form = await request.form()
        raw_files = form.getlist("files")
        if not raw_files:
            raw_files = form.getlist("file")

        uploaded_files = [f for f in raw_files if hasattr(f, "filename") and f.filename and hasattr(f, "read")]
        if not uploaded_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File upload is required for this importer",
            )

        accepted_types_lower = [t.lower() for t in importer.accepted_file_types] if importer.accepted_file_types else []

        for f in uploaded_files:
            if accepted_types_lower:
                ext = Path(f.filename or "").suffix.lower()
                if ext not in accepted_types_lower:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Unsupported file type. Allowed: {', '.join(importer.accepted_file_types)}",
                    )
            file_bytes = await f.read()
            if len(file_bytes) > settings.MAX_RECEIPT_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"File '{f.filename}' exceeds maximum allowed size of 20MB",
                )
            files_to_process.append((f.filename or "file", file_bytes))

    skipped_duplicates = 0
    failed_files: list[str] = []
    parsed_items: list[ImportedTransactionData] = []

    if importer.importer_id == "receipt_parser":
        # Pre-AI SHA-256 Deduplication
        files_with_hash = [(filename, f_bytes, f"sha256:{hashlib.sha256(f_bytes).hexdigest()}") for filename, f_bytes in files_to_process]
        candidate_hashes = {ext_id for _, _, ext_id in files_with_hash}
        existing_hashes: set[str] = set()

        if candidate_hashes:
            staged_existing = db.scalars(
                select(StagedTransaction.external_id).where(
                    StagedTransaction.source == importer.source_name,
                    StagedTransaction.external_id.in_(candidate_hashes),
                )
            ).all()
            tx_existing = db.scalars(
                select(Transaction.external_id).where(
                    Transaction.source == importer.source_name,
                    Transaction.external_id.in_(candidate_hashes),
                )
            ).all()
            existing_hashes.update(ext_id for ext_id in staged_existing if ext_id is not None)
            existing_hashes.update(ext_id for ext_id in tx_existing if ext_id is not None)

        seen_batch_hashes: set[str] = set()
        files_to_parse: list[tuple[str, bytes]] = []

        for filename, f_bytes, ext_id in files_with_hash:
            if ext_id in existing_hashes or ext_id in seen_batch_hashes:
                skipped_duplicates += 1
                continue
            seen_batch_hashes.add(ext_id)
            files_to_parse.append((filename, f_bytes))

        # Concurrency & Resilient execution
        semaphore = asyncio.Semaphore(settings.AI_MAX_BATCH_CONCURRENCY)

        async def parse_single_receipt(filename: str, f_bytes: bytes):
            async with semaphore:
                try:
                    items = await importer.fetch_and_parse(file_bytes=f_bytes, filename=filename)
                    return ("ok", filename, items)
                except (ImporterValidationError, ValueError, RuntimeError, Exception) as exc:
                    return ("error", filename, str(exc))

        results = await asyncio.gather(*(parse_single_receipt(fn, fb) for fn, fb in files_to_parse))
        for res_type, filename, payload in results:
            if res_type == "error":
                failed_files.append(f"{filename}: {payload}")
            else:
                parsed_items.extend(payload)
    elif importer.input_type == ImporterInputType.FILE:
        for filename, f_bytes in files_to_process:
            try:
                items = await importer.fetch_and_parse(file_bytes=f_bytes, filename=filename)
                parsed_items.extend(items)
            except ImporterValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
    else:
        try:
            parsed_items = await importer.fetch_and_parse()
        except ImporterValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    total_parsed = len(parsed_items)
    new_staged_records: list[StagedTransaction] = []

    # For non-receipt_parser importers, do post-parse deduplication
    if importer.importer_id != "receipt_parser":
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
        items_to_stage: list[ImportedTransactionData] = []
        for item in parsed_items:
            ext_id = item.external_id
            if ext_id is not None:
                if ext_id in seen_external_ids or ext_id in existing_ext_ids:
                    skipped_duplicates += 1
                    continue
                seen_external_ids.add(ext_id)
            items_to_stage.append(item)
    else:
        items_to_stage = parsed_items

    for item in items_to_stage:
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
            external_id=item.external_id,
            date=item.date,
            description=item.description,
            total_amount=item.total_amount,
            receipt_file_path=receipt_file_path,
            url=item.url,
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
        failed_files=failed_files,
    )
