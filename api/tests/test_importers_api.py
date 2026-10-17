from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.staged_transaction import StagedTransaction
from models.transaction import Transaction
from services.importers.base import (
    BaseImporter,
    ImportedTransactionData,
    ImporterInputType,
    ImporterReceiptData,
)
from services.importers.csv_base import BaseCsvImporter
from services.importers.registry import _IMPORTERS_BY_ID, register_importer

MOCK_ADMIN = "admin"
MOCK_PASSWORD = "admin"
MOCK_SECRET_KEY = "mock-secret-key-that-is-at-least-32-characters-long!"
MOCK_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def set_mock_env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", MOCK_ADMIN)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", MOCK_PASSWORD)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", MOCK_SECRET_KEY)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", MOCK_ALGORITHM)
    monkeypatch.setattr(settings, "RECEIPT_STORAGE_DIR", tmp_path / "receipts")


@pytest.fixture
def auth_headers():
    token = create_access_token(
        data={"sub": MOCK_ADMIN},
        secret_key=MOCK_SECRET_KEY,
        algorithm=MOCK_ALGORITHM,
        expires_delta=timedelta(minutes=60),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class MockCsvImporter(BaseCsvImporter):
    REQUIRED_COLUMNS = ("External ID", "Date", "Description", "Amount")

    @property
    def importer_id(self) -> str:
        return "mock_csv"

    @property
    def display_name(self) -> str:
        return "Mock CSV Importer"

    @property
    def description(self) -> str:
        return "Imports mock CSV transactions"

    def parse_row(self, row: dict[str, str], row_number: int) -> ImportedTransactionData | None:
        amount = self.parse_amount(row["Amount"])
        if self.SKIP_ZERO_AMOUNT_ROWS and amount == Decimal("0.00"):
            return None
        tx_date = self.parse_iso_or_common_date(row["Date"])
        return ImportedTransactionData(
            external_id=row.get("External ID") or None,
            date=tx_date,
            description=row["Description"],
            total_amount=amount,
            currency_code=row.get("Currency") or "USD",
        )


class MockIntegrationImporter(BaseImporter):
    def __init__(self, items: list[ImportedTransactionData] | None = None):
        self._items = items or []

    @property
    def importer_id(self) -> str:
        return "mock_integration"

    @property
    def display_name(self) -> str:
        return "Mock Integration Importer"

    @property
    def description(self) -> str:
        return "Pulls directly from integration"

    @property
    def input_type(self) -> ImporterInputType:
        return ImporterInputType.NONE

    @property
    def supports_mark_imported(self) -> bool:
        return True

    async def fetch_and_parse(
        self,
        file_bytes: bytes | None = None,
        filename: str | None = None,
    ) -> list[ImportedTransactionData]:
        return list(self._items)


@pytest.fixture
def registered_test_importers():
    saved = dict(_IMPORTERS_BY_ID)
    _IMPORTERS_BY_ID.clear()
    csv_imp = MockCsvImporter()
    int_imp = MockIntegrationImporter(
        items=[
            ImportedTransactionData(
                external_id="INT-1",
                date=date(2026, 10, 5),
                description="Integration Invoice",
                total_amount=Decimal("250.00"),
                receipt=ImporterReceiptData(
                    filename="invoice 123.pdf",
                    content=b"%PDF-1.4 mock receipt",
                ),
            ),
        ]
    )
    register_importer(csv_imp)
    register_importer(int_imp)
    try:
        yield csv_imp, int_imp
    finally:
        _IMPORTERS_BY_ID.clear()
        _IMPORTERS_BY_ID.update(saved)


def test_importers_unauthenticated_blocked(client):
    assert client.get("/api/importers").status_code == 401
    assert client.post("/api/importers/mock_csv/run").status_code == 401


def test_list_importers(client, auth_headers, registered_test_importers):
    res = client.get("/api/importers", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2

    assert data[0] == {
        "importer_id": "mock_csv",
        "source_name": "mock_csv",
        "display_name": "Mock CSV Importer",
        "description": "Imports mock CSV transactions",
        "input_type": "file",
        "accepted_file_types": [".csv"],
        "supports_mark_imported": False,
    }
    assert data[1] == {
        "importer_id": "mock_integration",
        "source_name": "mock_integration",
        "display_name": "Mock Integration Importer",
        "description": "Pulls directly from integration",
        "input_type": "none",
        "accepted_file_types": [],
        "supports_mark_imported": True,
    }


def test_run_importer_not_found_and_validation_errors(client, auth_headers, registered_test_importers):
    # Unknown importer -> 404
    res_404 = client.post("/api/importers/non_existent/run", headers=auth_headers)
    assert res_404.status_code == 404

    # FILE importer without multipart file -> 400
    res_no_file = client.post("/api/importers/mock_csv/run", headers=auth_headers)
    assert res_no_file.status_code == 400

    # FILE importer with invalid CSV columns -> 400
    res_bad_csv = client.post(
        "/api/importers/mock_csv/run",
        files={"file": ("bad.csv", b"WrongHeader\n123\n", "text/csv")},
        headers=auth_headers,
    )
    assert res_bad_csv.status_code == 400
    assert "Missing required CSV columns" in res_bad_csv.json()["detail"]


def test_run_csv_importer_and_deduplication(client, auth_headers, db_session, registered_test_importers):
    # Seed existing records across STAGED, ACCEPTED, DISMISSED, and Ledger Transaction
    db_session.add_all(
        [
            StagedTransaction(
                source="mock_csv",
                external_id="EXT-STAGED",
                date=date(2026, 10, 1),
                description="Already staged",
                total_amount=Decimal("10.00"),
                status="STAGED",
            ),
            StagedTransaction(
                source="mock_csv",
                external_id="EXT-ACCEPTED",
                date=date(2026, 10, 1),
                description="Already accepted",
                total_amount=Decimal("20.00"),
                status="ACCEPTED",
            ),
            StagedTransaction(
                source="mock_csv",
                external_id="EXT-DISMISSED",
                date=date(2026, 10, 1),
                description="Already dismissed",
                total_amount=Decimal("30.00"),
                status="DISMISSED",
            ),
            Transaction(
                source="mock_csv",
                external_id="EXT-LEDGER",
                date=date(2026, 10, 1),
                description="Already in ledger",
                total_amount=Decimal("40.00"),
            ),
        ]
    )
    db_session.commit()

    csv_content = (
        b"External ID,Date,Description,Amount\n"
        b"EXT-NEW-1,2026-10-02,New Item 1,55.00\n"
        b"EXT-NEW-1,2026-10-02,Intra-batch Dup,55.00\n"
        b"EXT-STAGED,2026-10-02,Dup Staged,10.00\n"
        b"EXT-ACCEPTED,2026-10-02,Dup Accepted,20.00\n"
        b"EXT-DISMISSED,2026-10-02,Dup Dismissed,30.00\n"
        b"EXT-LEDGER,2026-10-02,Dup Ledger,40.00\n"
        b",2026-10-03,No External ID Item,12.34\n"
    )

    res = client.post(
        "/api/importers/mock_csv/run",
        files={"file": ("import.csv", csv_content, "text/csv")},
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["importer_id"] == "mock_csv"
    assert body["total_parsed"] == 7
    assert body["staged_count"] == 2
    assert body["skipped_duplicates"] == 5
    assert len(body["items"]) == 2
    assert body["items"][0]["external_id"] == "EXT-NEW-1"
    assert body["items"][0]["status"] == "STAGED"
    assert body["items"][0]["is_ready"] is False
    assert body["items"][1]["external_id"] is None


def test_run_none_input_importer_with_receipt_persistence(client, auth_headers, registered_test_importers):
    res = client.post("/api/importers/mock_integration/run", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["importer_id"] == "mock_integration"
    assert body["total_parsed"] == 1
    assert body["staged_count"] == 1
    assert body["skipped_duplicates"] == 0

    item = body["items"][0]
    assert item["external_id"] == "INT-1"
    assert item["supports_mark_imported"] is True
    assert item["receipt_file_path"] is not None
    assert item["receipt_file_path"].endswith("_invoice_123.pdf")

    saved_file = settings.RECEIPT_STORAGE_DIR / item["receipt_file_path"]
    assert saved_file.is_file()
    assert saved_file.read_bytes() == b"%PDF-1.4 mock receipt"
