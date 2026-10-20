import hashlib
from pathlib import Path

from .base import (
    BaseImporter,
    ImportedTransactionData,
    ImporterInputType,
    ImporterReceiptData,
    ImporterValidationError,
)
from ..ai.factory import get_receipt_parser

MIME_TYPE_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


class ReceiptParserImporter(BaseImporter):
    """Importer that leverages AI providers to extract transaction data from receipt photos and PDFs."""

    @property
    def importer_id(self) -> str:
        return "receipt_parser"

    @property
    def source_name(self) -> str:
        return "receipt_parser"

    @property
    def display_name(self) -> str:
        return "Receipt Scanner (AI)"

    @property
    def description(self) -> str:
        return "Scan receipt photos (.png, .jpg, .webp) or PDFs into staging with attached files."

    @property
    def input_type(self) -> ImporterInputType:
        return ImporterInputType.FILE

    @property
    def accepted_file_types(self) -> list[str]:
        return [".jpg", ".jpeg", ".png", ".webp", ".pdf"]

    @property
    def supports_mark_imported(self) -> bool:
        return False

    async def fetch_and_parse(
        self,
        file_bytes: bytes | None = None,
        filename: str | None = None,
    ) -> list[ImportedTransactionData]:
        if not file_bytes:
            raise ImporterValidationError("Receipt file content is required")

        safe_filename = filename or "receipt"
        ext = Path(safe_filename).suffix.lower()
        mime_type = MIME_TYPE_MAP.get(ext)
        if not mime_type:
            raise ImporterValidationError(f"Unsupported file type: {ext}. Allowed: {', '.join(self.accepted_file_types)}")

        external_id = f"sha256:{hashlib.sha256(file_bytes).hexdigest()}"

        parser = get_receipt_parser()
        result = await parser.parse_receipt(file_bytes, safe_filename, mime_type)

        description = result.description or result.merchant or "Receipt"

        return [
            ImportedTransactionData(
                external_id=external_id,
                date=result.date,
                description=description,
                total_amount=result.total_amount,
                receipt=ImporterReceiptData(
                    filename=safe_filename,
                    content=file_bytes,
                    content_type=mime_type,
                ),
            )
        ]
