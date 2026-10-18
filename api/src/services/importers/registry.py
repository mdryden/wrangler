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
