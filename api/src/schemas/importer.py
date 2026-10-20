from pydantic import BaseModel, Field

from services.importers.base import ImporterInputType

from .staging import StagedTransactionResponse


class ImporterMetadataResponse(BaseModel):
    importer_id: str
    source_name: str
    display_name: str
    description: str
    input_type: ImporterInputType
    accepted_file_types: list[str]
    supports_mark_imported: bool


class ImporterRunResponse(BaseModel):
    importer_id: str
    total_parsed: int
    staged_count: int
    skipped_duplicates: int
    items: list[StagedTransactionResponse]
    failed_files: list[str] = Field(default_factory=list)
