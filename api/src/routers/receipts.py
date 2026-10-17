import mimetypes

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from services.receipts import get_receipt_file_path

router = APIRouter(prefix="/api/receipts", tags=["receipts"])

MEDIA_TYPE_MAP = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


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
