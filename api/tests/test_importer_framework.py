import asyncio
from datetime import date
from decimal import Decimal, InvalidOperation

import pytest
from pydantic import ValidationError

from services.importers.base import (
    BaseImporter,
    ImportedTransactionData,
    ImporterInputType,
    ImporterReceiptData,
    ImporterValidationError,
)
from services.importers.csv_base import BaseCsvImporter
from services.importers.registry import (
    _IMPORTERS_BY_ID,
    get_importer,
    get_importer_by_source,
    list_importers,
    register_importer,
)


def test_imported_transaction_data_valid():
    receipt = ImporterReceiptData(filename="invoice.pdf", content=b"%PDF-1.4")
    item = ImportedTransactionData(
        external_id="EXT-1",
        date=date(2026, 10, 1),
        description="  Cloud Hosting  ",
        total_amount=Decimal("42.50"),
        currency_code="CAD",
        receipt=receipt,
    )
    assert item.external_id == "EXT-1"
    assert item.date == date(2026, 10, 1)
    assert item.description == "Cloud Hosting"
    assert item.total_amount == Decimal("42.50")
    assert item.currency_code == "CAD"
    assert item.receipt == receipt
    assert item.receipt.content_type == "application/pdf"


def test_imported_transaction_data_nullable_and_defaults():
    # Whitespace-only description normalizes to None
    item1 = ImportedTransactionData(
        date=date(2026, 10, 1),
        description="   ",
        total_amount=Decimal("10.00"),
    )
    assert item1.description is None

    # description=None is accepted and remains None
    item2 = ImportedTransactionData(
        date=date(2026, 10, 1),
        description=None,
        total_amount=Decimal("10.00"),
    )
    assert item2.description is None

    # Zero amount normalizes to None (both Decimal and str representations)
    item3 = ImportedTransactionData(
        date=date(2026, 10, 1),
        description="Valid description",
        total_amount=Decimal("0.00"),
    )
    assert item3.total_amount is None

    item4 = ImportedTransactionData(
        date=date(2026, 10, 1),
        description="Valid description",
        total_amount="0",
    )
    assert item4.total_amount is None

    # total_amount=None is accepted and remains None
    item5 = ImportedTransactionData(
        date=date(2026, 10, 1),
        description="Valid description",
        total_amount=None,
    )
    assert item5.total_amount is None

    # date=None is accepted and remains None; default instantiation has None for optional fields
    item6 = ImportedTransactionData(date=None)
    assert item6.date is None
    assert item6.description is None
    assert item6.total_amount is None
    assert item6.external_id is None
    assert item6.currency_code == "CAD"
    assert item6.receipt is None


def test_imported_transaction_data_validation_errors():
    with pytest.raises((ValidationError, InvalidOperation)):
        ImportedTransactionData(
            total_amount="invalid",
        )


def test_base_importer_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseImporter()


def test_base_importer_default_properties_and_mark_as_imported_noop():
    class DummyImporter(BaseImporter):
        @property
        def importer_id(self) -> str:
            return "dummy_importer"

        @property
        def display_name(self) -> str:
            return "Dummy Importer"

        @property
        def description(self) -> str:
            return "Test importer"

        @property
        def input_type(self) -> ImporterInputType:
            return ImporterInputType.NONE

        async def fetch_and_parse(
            self,
            file_bytes: bytes | None = None,
            filename: str | None = None,
        ) -> list[ImportedTransactionData]:
            return [
                ImportedTransactionData(
                    external_id="D-1",
                    date=date(2026, 10, 1),
                    description="Dummy tx",
                    total_amount=Decimal("-15.00"),
                ),
            ]

    importer = DummyImporter()
    assert importer.importer_id == "dummy_importer"
    assert importer.source_name == "dummy_importer"
    assert importer.display_name == "Dummy Importer"
    assert importer.description == "Test importer"
    assert importer.input_type == ImporterInputType.NONE
    assert importer.accepted_file_types == []
    assert importer.supports_mark_imported is False

    items = asyncio.run(importer.fetch_and_parse())
    assert len(items) == 1
    assert items[0].total_amount == Decimal("-15.00")

    result = asyncio.run(importer.mark_as_imported(["D-1"]))
    assert result is None

    err = ImporterValidationError("Invalid CSV")
    assert str(err) == "Invalid CSV"


class SampleCsvImporter(BaseCsvImporter):
    REQUIRED_COLUMNS = ("External ID", "Date", "Description", "Amount")
    SKIP_ZERO_AMOUNT_ROWS = True

    @property
    def importer_id(self) -> str:
        return "sample_csv"

    @property
    def display_name(self) -> str:
        return "Sample CSV Importer"

    @property
    def description(self) -> str:
        return "Sample CSV test importer"

    def parse_row(self, row: dict[str, str], row_number: int) -> ImportedTransactionData | None:
        if row.get("Description") == "SKIP_ME":
            return None
        amount = self.parse_amount(row["Amount"])
        if self.SKIP_ZERO_AMOUNT_ROWS and amount == Decimal("0.00"):
            return None
        tx_date = self.parse_iso_or_common_date(row["Date"])
        return ImportedTransactionData(
            external_id=row.get("External ID") or None,
            date=tx_date,
            description=row["Description"],
            total_amount=amount,
            currency_code=row.get("Currency") or "CAD",
        )


def test_base_csv_importer_parse_amount_and_dates():
    assert BaseCsvImporter.parse_amount("$1,234.56") == Decimal("1234.56")
    assert BaseCsvImporter.parse_amount("CAD 45.00") == Decimal("45.00")
    assert BaseCsvImporter.parse_amount("USD -19.99") == Decimal("-19.99")
    assert BaseCsvImporter.parse_amount("(12.34)") == Decimal("-12.34")
    assert BaseCsvImporter.parse_amount("($1,000.50)") == Decimal("-1000.50")

    with pytest.raises(ValueError):
        BaseCsvImporter.parse_amount("")
    with pytest.raises(ValueError):
        BaseCsvImporter.parse_amount("not-a-number")

    assert BaseCsvImporter.parse_iso_or_common_date("2026-10-15") == date(2026, 10, 15)
    assert BaseCsvImporter.parse_iso_or_common_date("10/15/2026") == date(2026, 10, 15)
    assert BaseCsvImporter.parse_iso_or_common_date("2026/10/15") == date(2026, 10, 15)
    assert BaseCsvImporter.parse_iso_or_common_date("2026-10-15T14:22:00Z") == date(2026, 10, 15)
    assert BaseCsvImporter.parse_iso_or_common_date("2026-10-15T09:00:00-05:00") == date(2026, 10, 15)

    with pytest.raises(ValueError):
        BaseCsvImporter.parse_iso_or_common_date("")
    with pytest.raises(ValueError):
        BaseCsvImporter.parse_iso_or_common_date("15-10-2026")


def test_base_csv_importer_pipeline_utf8_bom_and_latin1():
    importer = SampleCsvImporter()
    assert importer.input_type == ImporterInputType.FILE
    assert importer.accepted_file_types == [".csv"]

    # UTF-8 with BOM, zero amount row, skipped row, parenthetical negative
    csv_text = (
        "\ufeff External ID , Date , Description , Amount , Currency \n"
        "TX-1, 2026-10-01, Coffee Shop, $12.50, USD\n"
        "TX-ZERO, 2026-10-02, Zero Row, 0.00, USD\n"
        "TX-SKIP, 2026-10-03, SKIP_ME, 50.00, USD\n"
        "TX-2, 10/04/2026, Refund Item, (25.00), CAD\n"
    )
    items = asyncio.run(importer.fetch_and_parse(csv_text.encode("utf-8")))
    assert len(items) == 2
    assert items[0].external_id == "TX-1"
    assert items[0].date == date(2026, 10, 1)
    assert items[0].description == "Coffee Shop"
    assert items[0].total_amount == Decimal("12.50")
    assert items[1].external_id == "TX-2"
    assert items[1].total_amount == Decimal("-25.00")
    assert items[1].currency_code == "CAD"

    # Latin-1 encoded content fallback
    latin1_csv = "External ID,Date,Description,Amount\nTX-3,2026-10-05,Café Boulangerie,15.00\n".encode("latin-1")
    latin1_items = asyncio.run(importer.fetch_and_parse(latin1_csv))
    assert len(latin1_items) == 1
    assert latin1_items[0].description == "Café Boulangerie"


def test_base_csv_importer_validation_errors():
    importer = SampleCsvImporter()

    # Empty bytes
    with pytest.raises(ImporterValidationError, match="CSV file is required and must not be empty"):
        asyncio.run(importer.fetch_and_parse(b""))

    # Missing required columns
    bad_headers = b"Date,Description\n2026-10-01,Test\n"
    with pytest.raises(ImporterValidationError, match="Missing required CSV columns: External ID, Amount"):
        asyncio.run(importer.fetch_and_parse(bad_headers))

    # Row-level error reporting (row 3 has invalid amount)
    bad_row = b"External ID,Date,Description,Amount\nTX-1,2026-10-01,Valid,10.00\nTX-2,2026-10-02,Invalid,abc\n"
    with pytest.raises(ImporterValidationError, match="Row 3:"):
        asyncio.run(importer.fetch_and_parse(bad_row))


def test_importer_registry():
    saved = dict(_IMPORTERS_BY_ID)
    _IMPORTERS_BY_ID.clear()
    try:
        imp = SampleCsvImporter()
        register_importer(imp)

        all_imps = list_importers()
        assert len(all_imps) == 1
        assert all_imps[0] is imp

        assert get_importer("sample_csv") is imp
        assert get_importer("unknown") is None

        assert get_importer_by_source("sample_csv") is imp
        assert get_importer_by_source("unknown_source") is None
    finally:
        _IMPORTERS_BY_ID.clear()
        _IMPORTERS_BY_ID.update(saved)


def test_staging_schemas_and_compute_staged_is_ready(db_session):
    import uuid

    from models.company import Company
    from models.staged_allocation import StagedAllocation
    from models.staged_transaction import StagedTransaction
    from schemas.staging import StagedAllocationItem, StagedTransactionUpdate, compute_staged_is_ready

    # Schema validation errors
    with pytest.raises(ValidationError):
        StagedAllocationItem(amount=Decimal("0.00"))

    with pytest.raises(ValidationError):
        StagedTransactionUpdate(description="   ")

    with pytest.raises(ValidationError):
        StagedTransactionUpdate(total_amount=Decimal("0.00"))

    company1 = Company(name="Ready Co 1")
    company2 = Company(name="Ready Co 2")
    db_session.add_all([company1, company2])
    db_session.commit()

    staged_tx = StagedTransaction(
        source="sample_csv",
        date=date(2026, 10, 1),
        description="Readiness test",
        total_amount=Decimal("100.00"),
        status="STAGED",
    )
    db_session.add(staged_tx)
    db_session.commit()
    db_session.refresh(staged_tx)

    # 1. Zero allocations -> not ready
    assert compute_staged_is_ready(staged_tx) is False

    # 2. Single personal allocation (company_id=None) -> ready
    staged_tx.allocations = [
        StagedAllocation(staged_transaction_id=staged_tx.id, amount=Decimal("100.00"), is_personal=True, company_id=None),
    ]
    assert compute_staged_is_ready(staged_tx) is True

    # 3. Single business allocation with company_id -> ready
    staged_tx.allocations = [
        StagedAllocation(staged_transaction_id=staged_tx.id, amount=Decimal("100.00"), is_personal=False, company_id=company1.id),
    ]
    assert compute_staged_is_ready(staged_tx) is True

    # 4. Unbalanced sum -> not ready
    staged_tx.allocations = [
        StagedAllocation(staged_transaction_id=staged_tx.id, amount=Decimal("60.00"), is_personal=False, company_id=company1.id),
    ]
    assert compute_staged_is_ready(staged_tx) is False

    # 5. Multi-split all business with company_id -> ready
    staged_tx.allocations = [
        StagedAllocation(staged_transaction_id=staged_tx.id, amount=Decimal("60.00"), is_personal=False, company_id=company1.id),
        StagedAllocation(staged_transaction_id=staged_tx.id, amount=Decimal("40.00"), is_personal=False, company_id=company2.id),
    ]
    assert compute_staged_is_ready(staged_tx) is True

    # 6. Multi-split containing personal -> not ready
    staged_tx.allocations = [
        StagedAllocation(staged_transaction_id=staged_tx.id, amount=Decimal("60.00"), is_personal=False, company_id=company1.id),
        StagedAllocation(staged_transaction_id=staged_tx.id, amount=Decimal("40.00"), is_personal=True, company_id=None),
    ]
    assert compute_staged_is_ready(staged_tx) is False

    # 7. Non-STAGED status -> not ready
    staged_tx.status = "ACCEPTED"
    staged_tx.allocations = [
        StagedAllocation(staged_transaction_id=staged_tx.id, amount=Decimal("100.00"), is_personal=True, company_id=None),
    ]
    assert compute_staged_is_ready(staged_tx) is False
    assert isinstance(uuid.uuid4(), uuid.UUID)
