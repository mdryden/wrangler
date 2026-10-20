import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from core.config import settings
from services.ai.base import ReceiptParseResult
from services.ai.factory import get_receipt_parser
from services.receipts import get_receipt_file_path

router = APIRouter(prefix="/api/receipts", tags=["receipts"])

MEDIA_TYPE_MAP = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

ALLOWED_RECEIPT_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}

EXTENSION_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


@router.post("/parse", response_model=ReceiptParseResult)
async def parse_receipt(file: UploadFile) -> ReceiptParseResult:
    """Parse receipt photo or PDF using configured AI provider."""
    file_bytes = await file.read()
    if len(file_bytes) > settings.MAX_RECEIPT_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Receipt file exceeds 20MB limit",
        )

    ext = Path(file.filename or "").suffix.lower()
    content_type = (file.content_type or "").lower().strip()
    if content_type not in ALLOWED_RECEIPT_MIME_TYPES:
        if ext in EXTENSION_TO_MIME:
            content_type = EXTENSION_TO_MIME[ext]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type. Allowed: .jpg, .jpeg, .png, .webp, .pdf",
            )
    else:
        if ext and ext not in EXTENSION_TO_MIME:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type. Allowed: .jpg, .jpeg, .png, .webp, .pdf",
            )

    try:
        parser = get_receipt_parser()
        return await parser.parse_receipt(
            file_bytes=file_bytes,
            filename=file.filename or "receipt",
            mime_type=content_type,
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


@router.get("/{file_path:path}")
def get_receipt(file_path: str) -> FileResponse:
    """Safely stream/serve receipt file from RECEIPT_STORAGE_DIR with inline disposition."""
    try:
        path = get_receipt_file_path(file_path)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    ext = path.suffix.lower()
    media_type = MEDIA_TYPE_MAP.get(ext) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        content_disposition_type="inline",
    )
