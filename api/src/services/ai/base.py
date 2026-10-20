import datetime
from abc import ABC, abstractmethod
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ReceiptParseResult(BaseModel):
    """Normalized structured data extracted from a receipt document."""

    merchant: str | None = Field(default=None, description="Clean name of the merchant or store")
    date: datetime.date | None = Field(default=None, description="Transaction date")
    total_amount: Decimal | None = Field(default=None, description="Final total amount charged")
    description: str | None = Field(
        default=None,
        description="Concise description formatted as '{Merchant} - {Summary of items purchased}'",
    )

    model_config = ConfigDict(from_attributes=True)


class BaseReceiptParserProvider(ABC):
    """Abstract base class for receipt parsing AI providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this AI provider (e.g., 'openai', 'mock')."""

    @abstractmethod
    async def parse_receipt(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> ReceiptParseResult:
        """Parse receipt file bytes and return structured receipt data.

        Raises:
            ValueError: If file format is unsupported or payload cannot be processed.
            RuntimeError: If upstream AI provider returns an unrecoverable API or authentication error.
        """
