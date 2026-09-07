from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class ParsedTransaction(BaseModel):
    """Normalized transaction data extracted by an intake parser."""

    source: str
    external_id: str | None = None
    date: date
    description: str
    total_amount: Decimal
    currency_code: str = "USD"
    receipt_file_path: str | None = None

    model_config = ConfigDict(from_attributes=True)


class BaseIntakeParser(ABC):
    """Abstract base class for parsing transactions from external intake sources."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """The source identifier (e.g., 'manual', 'amazon')."""
        pass

    @abstractmethod
    def parse(self, raw_data: Any) -> list[ParsedTransaction]:
        """Parse raw intake data and return a list of normalized ParsedTransaction objects."""
        pass


class ManualIntakeParser(BaseIntakeParser):
    """Default parser for manually entered transactions."""

    @property
    def source_name(self) -> str:
        return "manual"

    def parse(self, raw_data: Any) -> list[ParsedTransaction]:
        """Parse manual transaction data.

        Accepts a dictionary, a ParsedTransaction, or an iterable of such objects.
        """
        if isinstance(raw_data, list):
            items = raw_data
        else:
            items = [raw_data]

        results: list[ParsedTransaction] = []
        for item in items:
            if isinstance(item, ParsedTransaction):
                results.append(item)
            elif isinstance(item, dict):
                data = item.copy()
                data.setdefault("source", self.source_name)
                data.setdefault("currency_code", "USD")
                parsed = ParsedTransaction(**data)
                results.append(parsed)
            else:
                data = {
                    "source": getattr(item, "source", self.source_name),
                    "external_id": getattr(item, "external_id", None),
                    "date": getattr(item, "date", None),
                    "description": getattr(item, "description", None),
                    "total_amount": getattr(item, "total_amount", None),
                    "currency_code": getattr(item, "currency_code", "USD"),
                    "receipt_file_path": getattr(item, "receipt_file_path", None),
                }
                parsed = ParsedTransaction(**data)
                results.append(parsed)

        return results
