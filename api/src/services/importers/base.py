from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator


class ImporterValidationError(Exception):
    """Raised when an importer encounters invalid input or row data."""


class ImporterInputType(StrEnum):
    FILE = "file"
    NONE = "none"


class ImporterReceiptData(BaseModel):
    """Optional receipt file payload extracted directly by an importer."""

    filename: str
    content: bytes
    content_type: str = "application/pdf"


class ImportedTransactionData(BaseModel):
    """Normalized transaction item produced by an importer implementation."""

    external_id: str | None = None
    date: date
    description: str
    total_amount: Decimal
    currency_code: str = "CAD"
    receipt: ImporterReceiptData | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("description must not be empty")
        return cleaned

    @field_validator("total_amount")
    @classmethod
    def validate_total_amount(cls, v: Decimal) -> Decimal:
        if v == Decimal("0"):
            raise ValueError("total_amount must be strictly non-zero")
        return v


class BaseImporter(ABC):
    """Abstract base class for all transaction importers."""

    @property
    @abstractmethod
    def importer_id(self) -> str:
        """Unique URL-safe identifier for this importer."""

    @property
    def source_name(self) -> str:
        """Source name persisted on StagedTransaction and Transaction records."""
        return self.importer_id

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief UI help text explaining what this importer reads."""

    @property
    @abstractmethod
    def input_type(self) -> ImporterInputType:
        """Input type required by this importer (FILE or NONE)."""

    @property
    def accepted_file_types(self) -> list[str]:
        """List of accepted file extensions when input_type == FILE."""
        return []

    @property
    def supports_mark_imported(self) -> bool:
        """Whether this importer marks records as imported in the external source system."""
        return False

    @abstractmethod
    async def fetch_and_parse(
        self,
        file_bytes: bytes | None = None,
        filename: str | None = None,
    ) -> list[ImportedTransactionData]:
        """Validate input requirements and return normalized transaction items."""

    async def mark_as_imported(self, external_ids: list[str]) -> None:
        """Mark external IDs as imported in the source system (defaults to a no-op)."""
        return None
