import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from core.config import settings


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing path components and restricting characters."""
    base_name = Path(filename).name
    # Keep alphanumeric, dashes, underscores, and dots
    sanitized = re.sub(r"[^\w\-.]", "_", base_name)
    return sanitized if sanitized else "receipt"


async def save_receipt_file(file: UploadFile, transaction_id: uuid.UUID) -> str:
    """Save an uploaded receipt file into RECEIPT_STORAGE_DIR and return the relative filename."""
    settings.RECEIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "receipt"
    safe_name = sanitize_filename(original_name)
    unique_filename = f"{transaction_id}_{safe_name}"
    target_path = settings.RECEIPT_STORAGE_DIR / unique_filename

    content = await file.read()
    target_path.write_bytes(content)

    return unique_filename


def get_receipt_file_path(file_path: str) -> Path:
    """Resolve and validate a receipt file path within RECEIPT_STORAGE_DIR, preventing path traversal."""
    cleaned = file_path.lstrip("/\\")
    if cleaned.startswith("receipts/"):
        cleaned = cleaned[len("receipts/") :]
    elif cleaned.startswith("receipts\\"):
        cleaned = cleaned[len("receipts\\") :]

    base_dir = settings.RECEIPT_STORAGE_DIR.resolve()
    target_path = (base_dir / cleaned).resolve()

    if not target_path.is_relative_to(base_dir):
        raise ValueError(f"Directory traversal detected or invalid receipt path: '{file_path}'")

    if not target_path.is_file():
        raise FileNotFoundError(f"Receipt file not found: '{file_path}'")

    return target_path
