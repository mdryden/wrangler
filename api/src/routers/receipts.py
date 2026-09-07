from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from services.receipts import get_receipt_file_path

router = APIRouter(prefix="/api/receipts", tags=["receipts"])


@router.get("/{file_path:path}")
def get_receipt(file_path: str):
    """Safely stream/serve receipt file from RECEIPT_STORAGE_DIR."""
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

    return FileResponse(path)
