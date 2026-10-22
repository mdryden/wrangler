from .ai_receipt import ReceiptParserImporter
from .amazon_csv import AmazonCsvImporter
from .base import BaseImporter

_IMPORTERS_BY_ID: dict[str, BaseImporter] = {}


def register_importer(importer: BaseImporter) -> None:
    """Register a BaseImporter instance in the global registry."""
    _IMPORTERS_BY_ID[importer.importer_id] = importer


def list_importers() -> list[BaseImporter]:
    """Return all registered importers in registration order."""
    return list(_IMPORTERS_BY_ID.values())


def get_importer(importer_id: str) -> BaseImporter | None:
    """Look up a registered importer by its importer_id."""
    return _IMPORTERS_BY_ID.get(importer_id)


def get_importer_by_source(source_name: str) -> BaseImporter | None:
    """Look up a registered importer by its source_name."""
    for importer in _IMPORTERS_BY_ID.values():
        if importer.source_name == source_name:
            return importer
    return None


# Register default system importers
register_importer(AmazonCsvImporter())
register_importer(ReceiptParserImporter())

SOURCE_FRIENDLY_NAMES: dict[str, str] = {
    "amazon_csv": "Amazon",
    "receipt_parser": "Receipt",
    "ai_receipt": "Receipt",
    "mcp": "AI Assistant",
    "manual": "Manual",
    "wrangler_csv": "Wrangler",
    "google_groups": "Google Groups",
}


def get_source_friendly_name(source: str) -> str:
    """Return friendly display name for source, falling back to title-cased source name."""
    return SOURCE_FRIENDLY_NAMES.get(source, source.replace("_", " ").title())


def format_personal_fallback_description(source: str) -> str:
    """Generate clean fallback description for personal transactions."""
    return f"{get_source_friendly_name(source)}: Personal"
