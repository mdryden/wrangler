import datetime
from abc import ABC, abstractmethod
from decimal import Decimal
from enum import StrEnum
from typing import Any

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
    date: datetime.date | None = None
    description: str | None = None
    total_amount: Decimal | None = None
    currency_code: str = "CAD"
    receipt: ImporterReceiptData | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, v: Any) -> str | None:
        if v is None:
            return None
        cleaned = str(v).strip()
        return cleaned if cleaned else None

    @field_validator("total_amount", mode="before")
    @classmethod
    def validate_total_amount(cls, v: Any) -> Decimal | None:
        if v is None:
            return None
        dec = Decimal(str(v))
        if dec == Decimal("0"):
            return None
        return dec


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
