import datetime
import re
from decimal import Decimal

from .base import BaseReceiptParserProvider, ReceiptParseResult


class MockReceiptParser(BaseReceiptParserProvider):
    """Deterministic mock receipt parser for testing and development."""

    @property
    def provider_id(self) -> str:
        return "mock"

    async def parse_receipt(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> ReceiptParseResult:
        filename_lower = filename.lower()

        if any(keyword in filename_lower for keyword in ("corrupt", "invalid", "fail")):
            raise ValueError(f"Corrupt or unreadable document: {filename}")

        if "timeout" in filename_lower:
            raise RuntimeError("AI provider request timed out")

        merchant = "Sample Store"
        date = datetime.date.today()
        description = f"{merchant} - Office supplies"

        if "missing_total" in filename_lower:
            total_amount = None
        else:
            match = re.search(r"(\d+)[._](\d{2})", filename)
            if match:
                total_amount = Decimal(f"{match.group(1)}.{match.group(2)}")
            else:
                total_amount = Decimal("45.99")

        return ReceiptParseResult(
            merchant=merchant,
            date=date,
            total_amount=total_amount,
            description=description,
        )
