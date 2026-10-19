import csv
import io
from abc import abstractmethod
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from .base import BaseImporter, ImportedTransactionData, ImporterInputType, ImporterValidationError


class BaseCsvImporter(BaseImporter):
    """Shared base class for all CSV-based transaction importers."""

    REQUIRED_COLUMNS: tuple[str, ...] = ()
    SKIP_ZERO_AMOUNT_ROWS: bool = True

    @property
    def input_type(self) -> ImporterInputType:
        return ImporterInputType.FILE

    @property
    def accepted_file_types(self) -> list[str]:
        return [".csv"]

    @staticmethod
    def parse_amount(raw: str) -> Decimal:
        """Strip currency prefixes/symbols, commas, whitespace, and handle parenthetical negatives."""
        if raw is None:
            raise ValueError("Amount is required")
        cleaned = raw.strip()
        if not cleaned:
            raise ValueError("Amount must not be empty")

        is_negative = False
        if cleaned.startswith("(") and cleaned.endswith(")"):
            is_negative = True
            cleaned = cleaned[1:-1].strip()

        if cleaned.startswith("-"):
            is_negative = True
            cleaned = cleaned[1:].strip()
        elif cleaned.startswith("+"):
            cleaned = cleaned[1:].strip()

        # Strip common currency symbols ($ and CA$) and commas
        cleaned = cleaned.replace("CA$", "").replace("ca$", "").replace("$", "").replace(",", "").strip()

        if cleaned.startswith("-"):
            is_negative = True
            cleaned = cleaned[1:].strip()
        elif cleaned.startswith("+"):
            cleaned = cleaned[1:].strip()

        if not cleaned:
            raise ValueError(f"Invalid amount value: '{raw}'")

        try:
            amount = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid amount value: '{raw}'") from exc

        if is_negative and amount > Decimal("0"):
            amount = -amount

        return amount.quantize(Decimal("0.01"))

    @staticmethod
    def parse_iso_or_common_date(raw: str) -> date:
        """Parse YYYY-MM-DD, MM/DD/YYYY, YYYY/MM/DD, or ISO timestamps."""
        if raw is None:
            raise ValueError("Date is required")
        cleaned = raw.strip()
        if not cleaned:
            raise ValueError("Date must not be empty")

        # Try common explicit date formats first
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue

        # Try ISO timestamp parsing (e.g., 2026-10-01T14:30:00Z or 2026-10-01T14:30:00-05:00)
        try:
            iso_candidate = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
            return datetime.fromisoformat(iso_candidate).date()
        except ValueError as exc:
            raise ValueError(f"Invalid date format: '{raw}'") from exc

    @abstractmethod
    def parse_row(self, row: dict[str, str], row_number: int) -> ImportedTransactionData | None:
        """Parse a normalized CSV row dict into an ImportedTransactionData or None to skip."""

    async def fetch_and_parse(
        self,
        file_bytes: bytes | None = None,
        filename: str | None = None,
    ) -> list[ImportedTransactionData]:
        if not file_bytes:
            raise ImporterValidationError("CSV file is required and must not be empty")

        try:
            decoded_text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded_text = file_bytes.decode("latin-1")

        if not decoded_text.strip():
            raise ImporterValidationError("CSV file is required and must not be empty")

        reader = csv.DictReader(io.StringIO(decoded_text))
        if reader.fieldnames is None:
            raise ImporterValidationError("CSV file is required and must not be empty")

        normalized_headers = [h.strip() for h in reader.fieldnames if h is not None]
        header_set = set(normalized_headers)
        missing = [col for col in self.REQUIRED_COLUMNS if col not in header_set]
        if missing:
            raise ImporterValidationError(f"Missing required CSV columns: {', '.join(missing)}")

        items: list[ImportedTransactionData] = []
        for row_number, raw_row in enumerate(reader, start=2):
            normalized_row: dict[str, str] = {}
            for key, val in raw_row.items():
                if key is not None:
                    normalized_row[key.strip()] = (val or "").strip()

            # Skip completely blank lines
            if not any(normalized_row.values()):
                continue

            try:
                parsed = self.parse_row(normalized_row, row_number)
            except ImporterValidationError:
                raise
            except (ValueError, ValidationError) as err:
                raise ImporterValidationError(f"Row {row_number}: {err}") from err

            if parsed is None:
                continue

            items.append(parsed)

        return items
