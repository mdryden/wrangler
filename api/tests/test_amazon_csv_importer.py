import asyncio
import io
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.company import Company
from models.staged_transaction import StagedTransaction
from models.transaction import Transaction
from services.importers.amazon_csv import AmazonCsvImporter
from services.importers.base import ImporterInputType, ImporterValidationError
from services.importers.registry import get_importer, list_importers

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


def test_amazon_csv_importer_metadata():
    importer = AmazonCsvImporter()
    assert importer.importer_id == "amazon_csv"
    assert importer.source_name == "amazon_csv"
    assert importer.display_name == "Amazon Transactions CSV"
    assert importer.description == "Imports Amazon orders and refunds from an exported Amazon transactions CSV file."
    assert importer.input_type == ImporterInputType.FILE
    assert importer.accepted_file_types == [".csv"]
    assert importer.supports_mark_imported is False
    assert importer.REQUIRED_COLUMNS == (
        "date",
        "order ids",
        "order urls",
        "vendor",
        "card_details",
        "amount",
    )
    assert importer.SKIP_ZERO_AMOUNT_ROWS is False
    assert asyncio.run(importer.mark_as_imported(["dummy-id"])) is None


def test_amazon_csv_importer_required_column_validation():
    importer = AmazonCsvImporter()

    # Empty bytes
    with pytest.raises(ImporterValidationError, match="CSV file is required and must not be empty"):
        asyncio.run(importer.fetch_and_parse(b""))

    # Missing required columns
    bad_csv = b"date,order ids,amount\n2026-10-16,ORDER-1,-96.04\n"
    with pytest.raises(ImporterValidationError, match="Missing required CSV columns: order urls, vendor, card_details"):
        asyncio.run(importer.fetch_and_parse(bad_csv))


def test_amazon_csv_importer_repeated_header_skipping():
    importer = AmazonCsvImporter()

    # Direct parse_row calls
    assert importer.parse_row({"date": "date", "order ids": "order ids"}, 2) is None
    assert importer.parse_row({"date": "Date ", "order ids": " 123-456 "}, 3) is None
    assert importer.parse_row({"date": "2026-10-16", "order ids": " ORDER IDS "}, 4) is None

    # Embedded in CSV pipeline
    csv_content = (
        b"date,order ids,order urls,vendor,card_details,amount\n"
        b"2026-10-16,ORDER-1,https://amazon.ca/...,Amazon.ca,Mastercard ****9145,-50.00\n"
        b"date,order ids,order urls,vendor,card_details,amount\n"
        b"2026-10-17,ORDER-2,https://amazon.ca/...,Amazon.ca,Mastercard ****9145,-25.00\n"
        b"DATE,ORDER IDS,order urls,vendor,card_details,amount\n"
    )

    items = asyncio.run(importer.fetch_and_parse(csv_content))
    assert len(items) == 2
    assert items[0].external_id == "ORDER-1_2026-10-16_50.00"
    assert items[1].external_id == "ORDER-2_2026-10-17_25.00"


def test_amazon_csv_importer_amount_sign_inversion():
    importer = AmazonCsvImporter()

    # Negative purchase becomes positive
    row1 = {
        "date": "2026-10-16",
        "order ids": "ORD-1",
        "order urls": "",
        "vendor": "Amazon",
        "card_details": "MC",
        "amount": "-96.04",
    }
    item1 = importer.parse_row(row1, 2)
    assert item1 is not None
    assert item1.total_amount == Decimal("96.04")

    # Positive refund becomes negative
    row2 = {**row1, "amount": "15.00"}
    item2 = importer.parse_row(row2, 3)
    assert item2 is not None
    assert item2.total_amount == Decimal("-15.00")

    # Formatted amounts with commas, currency symbols, explicit signs, parentheticals
    row3 = {**row1, "amount": "-$1,234.56"}
    item3 = importer.parse_row(row3, 4)
    assert item3 is not None
    assert item3.total_amount == Decimal("1234.56")

    row4 = {**row1, "amount": "+$50.00"}
    item4 = importer.parse_row(row4, 5)
    assert item4 is not None
    assert item4.total_amount == Decimal("-50.00")

    row5 = {**row1, "amount": "($25.50)"}
    item5 = importer.parse_row(row5, 6)
    assert item5 is not None
    assert item5.total_amount == Decimal("25.50")


def test_amazon_csv_importer_blank_description():
    importer = AmazonCsvImporter()
    row = {
        "date": "2026-10-16",
        "order ids": "ORD-1",
        "order urls": "https://amazon.ca",
        "vendor": "Amazon.ca",
        "card_details": "Mastercard",
        "amount": "-42.00",
    }
    item = importer.parse_row(row, 2)
    assert item is not None
    assert item.description is None


def test_amazon_csv_importer_fallback_resilience_no_dropped_rows():
    importer = AmazonCsvImporter()

    # Malformed date, blank amount
    row1 = {
        "date": "unparseable-date",
        "order ids": "ORD-FALLBACK-1",
        "order urls": "",
        "vendor": "Amazon",
        "card_details": "MC",
        "amount": "",
    }
    item1 = importer.parse_row(row1, 2)
    assert item1 is not None
    assert item1.date is None
    assert item1.total_amount is None
    assert item1.external_id == "ORD-FALLBACK-1_nodate_noamount"

    # Blank date, zero amount
    row2 = {
        "date": "",
        "order ids": "ORD-FALLBACK-2",
        "order urls": "",
        "vendor": "Amazon",
        "card_details": "MC",
        "amount": "0.00",
    }
    item2 = importer.parse_row(row2, 3)
    assert item2 is not None
    assert item2.date is None
    assert item2.total_amount is None
    assert item2.external_id == "ORD-FALLBACK-2_nodate_noamount"

    # Malformed amount
    row3 = {
        "date": "2026-10-16",
        "order ids": "ORD-FALLBACK-3",
        "order urls": "",
        "vendor": "Amazon",
        "card_details": "MC",
        "amount": "invalid-amount",
    }
    item3 = importer.parse_row(row3, 4)
    assert item3 is not None
    assert item3.date == date(2026, 10, 16)
    assert item3.total_amount is None
    assert item3.external_id == "ORD-FALLBACK-3_2026-10-16_noamount"

    # Multi-order string preserved
    row4 = {
        "date": "2026-09-19",
        "order ids": "D01-0626645-1689808, ??",
        "order urls": "https://amazon.ca",
        "vendor": "??",
        "card_details": "MC",
        "amount": "-27.25",
    }
    item4 = importer.parse_row(row4, 5)
    assert item4 is not None
    assert item4.external_id == "D01-0626645-1689808, ??_2026-09-19_27.25"

    # Blank order ids sets external_id to None
    row5 = {
        "date": "2026-10-16",
        "order ids": "   ",
        "order urls": "",
        "vendor": "Amazon",
        "card_details": "MC",
        "amount": "-10.00",
    }
    item5 = importer.parse_row(row5, 6)
    assert item5 is not None
    assert item5.external_id is None


def test_amazon_csv_importer_sample_csv_pipeline():
    importer = AmazonCsvImporter()
    sample_csv = (
        b"date,order ids,order urls,vendor,card_details,amount\n"
        b"2026-10-16,702-6236836-4669054,https://amazon.ca/...,Amazon.ca,Mastercard ****9145,-96.04\n"
        b"2026-10-12,702-4929086-4929052,https://amazon.ca/...,AMZN Mktp CA,Mastercard ****9145,-15.67\n"
        b'2026-09-19,"D01-0626645-1689808, ??","https://amazon.ca/...",??,Mastercard ****9145,-27.25\n'
        b"2026-09-10,702-1234567-8901234,https://amazon.ca/...,Amazon.ca,Mastercard ****9145,15.00\n"
        b"date,order ids,order urls,vendor,card_details,amount\n"
    )

    items = asyncio.run(importer.fetch_and_parse(sample_csv))
    assert len(items) == 4

    assert items[0].external_id == "702-6236836-4669054_2026-10-16_96.04"
    assert items[0].date == date(2026, 10, 16)
    assert items[0].description is None
    assert items[0].total_amount == Decimal("96.04")
    assert items[0].receipt is None

    assert items[1].external_id == "702-4929086-4929052_2026-10-12_15.67"
    assert items[1].date == date(2026, 10, 12)
    assert items[1].description is None
    assert items[1].total_amount == Decimal("15.67")
    assert items[1].receipt is None

    assert items[2].external_id == "D01-0626645-1689808, ??_2026-09-19_27.25"
    assert items[2].date == date(2026, 9, 19)
    assert items[2].description is None
    assert items[2].total_amount == Decimal("27.25")
    assert items[2].receipt is None

    assert items[3].external_id == "702-1234567-8901234_2026-09-10_-15.00"
    assert items[3].date == date(2026, 9, 10)
    assert items[3].description is None
    assert items[3].total_amount == Decimal("-15.00")
    assert items[3].receipt is None


def test_amazon_csv_importer_registered_and_discovery(client, auth_headers):
    # Registry checks
    registered = get_importer("amazon_csv")
    assert registered is not None
    assert isinstance(registered, AmazonCsvImporter)
    assert any(imp.importer_id == "amazon_csv" for imp in list_importers())

    # Discovery API check
    resp = client.get("/api/importers", headers=auth_headers)
    assert resp.status_code == 200
    importers = resp.json()
    match = next((item for item in importers if item["importer_id"] == "amazon_csv"), None)
    assert match is not None
    assert match == {
        "importer_id": "amazon_csv",
        "source_name": "amazon_csv",
        "display_name": "Amazon Transactions CSV",
        "description": "Imports Amazon orders and refunds from an exported Amazon transactions CSV file.",
        "input_type": "file",
        "accepted_file_types": [".csv"],
        "supports_mark_imported": False,
    }


def test_amazon_csv_importer_run_api_and_staging(client, auth_headers, db_session):
    csv_bytes = (
        b"date,order ids,order urls,vendor,card_details,amount\n"
        b"2026-10-16,702-6236836-4669054,https://amazon.ca/...,Amazon.ca,Mastercard ****9145,-96.04\n"
        b"2026-10-12,702-4929086-4929052,https://amazon.ca/...,AMZN Mktp CA,Mastercard ****9145,-15.67\n"
        b'2026-09-19,"D01-0626645-1689808, ??","https://amazon.ca/...",??,Mastercard ****9145,-27.25\n'
        b"2026-09-10,702-1234567-8901234,https://amazon.ca/...,Amazon.ca,Mastercard ****9145,15.00\n"
        b"date,order ids,order urls,vendor,card_details,amount\n"
    )

    resp = client.post(
        "/api/importers/amazon_csv/run",
        headers=auth_headers,
        files={"file": ("amazon.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["importer_id"] == "amazon_csv"
    assert data["total_parsed"] == 4
    assert data["staged_count"] == 4
    assert data["skipped_duplicates"] == 0
    assert len(data["items"]) == 4

    # Verify staging records in response
    items = data["items"]
    assert items[0]["external_id"] == "702-6236836-4669054_2026-10-16_96.04"
    assert items[0]["total_amount"] == "96.04"
    assert items[0]["description"] is None
    assert items[0]["source"] == "amazon_csv"
    assert items[0]["is_ready"] is False
    assert items[0]["status"] == "STAGED"

    assert items[3]["external_id"] == "702-1234567-8901234_2026-09-10_-15.00"
    assert items[3]["total_amount"] == "-15.00"
    assert items[3]["description"] is None
    assert items[3]["is_ready"] is False

    # Verify records persisted in DB
    persisted = db_session.query(StagedTransaction).filter_by(source="amazon_csv").all()
    assert len(persisted) == 4
    for stx in persisted:
        assert stx.source == "amazon_csv"
        assert stx.status == "STAGED"
        assert stx.description is None


def test_amazon_csv_importer_deduplication(client, auth_headers, db_session):
    # Pre-populate existing records across staged statuses and ledger
    staged_active = StagedTransaction(
        source="amazon_csv",
        external_id="EXISTING-STAGED_2026-10-10_10.00",
        date=date(2026, 10, 10),
        description="Active staged",
        total_amount=Decimal("10.00"),
        status="STAGED",
    )
    staged_accepted = StagedTransaction(
        source="amazon_csv",
        external_id="EXISTING-ACCEPTED_2026-10-10_20.00",
        date=date(2026, 10, 10),
        description="Accepted staged",
        total_amount=Decimal("20.00"),
        status="ACCEPTED",
    )
    staged_dismissed = StagedTransaction(
        source="amazon_csv",
        external_id="EXISTING-DISMISSED_2026-10-10_30.00",
        date=date(2026, 10, 10),
        description="Dismissed staged",
        total_amount=Decimal("30.00"),
        status="DISMISSED",
    )
    ledger_tx = Transaction(
        id=uuid.uuid4(),
        source="amazon_csv",
        external_id="EXISTING-LEDGER_2026-10-10_40.00",
        date=date(2026, 10, 10),
        description="Ledger tx",
        total_amount=Decimal("40.00"),
    )
    db_session.add_all([staged_active, staged_accepted, staged_dismissed, ledger_tx])
    db_session.commit()

    # CSV with:
    # - 4 cross-table duplicates (identical composite IDs)
    # - 2 rows sharing the SAME order id but DIFFERENT amounts (order charge + refund) -> both stage!
    # - 1 intra-batch exact duplicate (same order ID, date, amount twice) -> 1 stages, 1 skipped
    # - 1 row with empty order id -> always stages
    csv_bytes = (
        b"date,order ids,order urls,vendor,card_details,amount\n"
        b"2026-10-10,EXISTING-STAGED,url,vendor,card,-10.00\n"
        b"2026-10-10,EXISTING-ACCEPTED,url,vendor,card,-20.00\n"
        b"2026-10-10,EXISTING-DISMISSED,url,vendor,card,-30.00\n"
        b"2026-10-10,EXISTING-LEDGER,url,vendor,card,-40.00\n"
        b"2026-10-10,ORDER-SPLIT,url,vendor,card,-75.00\n"
        b"2026-10-10,ORDER-SPLIT,url,vendor,card,25.00\n"
        b"2026-10-10,DUP-EXACT,url,vendor,card,-50.00\n"
        b"2026-10-10,DUP-EXACT,url,vendor,card,-50.00\n"
        b"2026-10-10,,url,vendor,card,-60.00\n"
    )

    resp = client.post(
        "/api/importers/amazon_csv/run",
        headers=auth_headers,
        files={"file": ("amazon.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_parsed"] == 9
    # 4 cross duplicates skipped + 1 second DUP-EXACT skipped = 5 skipped
    assert data["skipped_duplicates"] == 5
    # Staged: 2 ORDER-SPLIT rows + 1 first DUP-EXACT + 1 blank order id = 4 staged
    assert data["staged_count"] == 4

    # Re-uploading the exact same CSV
    resp_again = client.post(
        "/api/importers/amazon_csv/run",
        headers=auth_headers,
        files={"file": ("amazon.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp_again.status_code == 200
    data_again = resp_again.json()
    assert data_again["total_parsed"] == 9
    # 4 cross-table + 2 ORDER-SPLIT + 2 DUP-EXACT = 8 duplicates skipped
    assert data_again["skipped_duplicates"] == 8
    # Only the blank external_id row stages again
    assert data_again["staged_count"] == 1


def test_amazon_csv_importer_staging_readiness_and_acceptance(client, auth_headers, db_session):
    company = Company(name="Amazon Supplies Co")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    csv_bytes = b"date,order ids,order urls,vendor,card_details,amount\n2026-10-16,702-READY-TEST,url,Amazon.ca,card,-45.50\n"

    resp = client.post(
        "/api/importers/amazon_csv/run",
        headers=auth_headers,
        files={"file": ("amazon.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    staged_items = resp.json()["items"]
    staged_id = staged_items[0]["id"]
    assert staged_items[0]["is_ready"] is False
    assert staged_items[0]["description"] is None
    assert staged_items[0]["total_amount"] == "45.50"

    # Acceptance guard: rejecting when not ready (description is None)
    accept_resp = client.post(
        "/api/staging/accept",
        headers=auth_headers,
        json={"staged_transaction_ids": [staged_id]},
    )
    assert accept_resp.status_code == 400
    assert "not ready for acceptance" in accept_resp.json()["detail"]

    # Update description and provide valid allocation
    update_payload = {
        "description": "Printer Paper and Ink",
        "allocations": [
            {
                "amount": "45.50",
                "is_personal": False,
                "company_id": str(company.id),
            }
        ],
    }
    update_resp = client.put(f"/api/staging/{staged_id}", headers=auth_headers, json=update_payload)
    assert update_resp.status_code == 200
    updated_data = update_resp.json()
    assert updated_data["description"] == "Printer Paper and Ink"
    assert updated_data["is_ready"] is True

    # Now accept into ledger
    accept_success = client.post(
        "/api/staging/accept",
        headers=auth_headers,
        json={"staged_transaction_ids": [staged_id]},
    )
    assert accept_success.status_code == 200
    acc_data = accept_success.json()
    assert acc_data["accepted_count"] == 1
    ledger_tx_id = acc_data["ledger_transaction_ids"][0]

    # Verify ledger record
    ledger_tx = db_session.get(Transaction, uuid.UUID(ledger_tx_id))
    assert ledger_tx is not None
    assert ledger_tx.source == "amazon_csv"
    assert ledger_tx.external_id == "702-READY-TEST_2026-10-16_45.50"
    assert ledger_tx.description == "Printer Paper and Ink"
    assert ledger_tx.total_amount == Decimal("45.50")
    assert len(ledger_tx.allocations) == 1
    assert ledger_tx.allocations[0].company_id == company.id


def test_amazon_csv_importer_vendor_filtering():
    importer = AmazonCsvImporter()
    base_row = {
        "date": "2026-10-18",
        "order ids": "702-VENDOR-1",
        "order urls": "https://amazon.ca/orders/1",
        "vendor": "Amazon.ca",
        "card_details": "Mastercard ****1234",
        "amount": "-50.00",
    }

    # PrimeVideo variations
    assert importer.parse_row({**base_row, "vendor": "PrimeVideo"}, 2) is None
    assert importer.parse_row({**base_row, "vendor": "Amazon PrimeVideo CA"}, 3) is None

    # Audible variations
    assert importer.parse_row({**base_row, "vendor": "Audible"}, 4) is None
    assert importer.parse_row({**base_row, "vendor": "Audible.ca"}, 5) is None

    # Permitted vendors parse normally
    item_amzn = importer.parse_row({**base_row, "vendor": "Amazon.ca"}, 6)
    assert item_amzn is not None
    assert item_amzn.total_amount == Decimal("50.00")

    item_mktp = importer.parse_row({**base_row, "vendor": "AMZN Mktp CA"}, 7)
    assert item_mktp is not None
    assert item_mktp.total_amount == Decimal("50.00")

    # Case sensitivity: lowercase "primevideo" is NOT skipped
    item_lower = importer.parse_row({**base_row, "vendor": "primevideo"}, 8)
    assert item_lower is not None
    assert item_lower.total_amount == Decimal("50.00")


def test_amazon_csv_importer_url_extraction():
    importer = AmazonCsvImporter()
    base_row = {
        "date": "2026-10-18",
        "order ids": "702-URL-1",
        "vendor": "Amazon.ca",
        "card_details": "Mastercard ****1234",
        "amount": "-25.00",
    }

    # Single URL
    row1 = {**base_row, "order urls": "https://www.amazon.ca/gp/your-account/order-details?orderID=702-123"}
    item1 = importer.parse_row(row1, 2)
    assert item1 is not None
    assert item1.url == "https://www.amazon.ca/gp/your-account/order-details?orderID=702-123"

    # Comma-separated URLs: first URL extracted
    row2 = {**base_row, "order urls": "https://amazon.ca/order1, https://amazon.ca/order2"}
    item2 = importer.parse_row(row2, 3)
    assert item2 is not None
    assert item2.url == "https://amazon.ca/order1"

    # Quoted comma-separated URLs: first URL extracted without quotes
    row3 = {**base_row, "order urls": '"https://amazon.ca/order1", "https://amazon.ca/order2"'}
    item3 = importer.parse_row(row3, 4)
    assert item3 is not None
    assert item3.url == "https://amazon.ca/order1"

    # Empty and whitespace-only URLs normalize to None
    row4 = {**base_row, "order urls": ""}
    item4 = importer.parse_row(row4, 5)
    assert item4 is not None
    assert item4.url is None

    row5 = {**base_row, "order urls": "    "}
    item5 = importer.parse_row(row5, 6)
    assert item5 is not None
    assert item5.url is None


def test_amazon_csv_importer_pipeline_url_persistence_and_vendor_filtering(client, auth_headers, db_session):
    csv_bytes = (
        b"date,order ids,order urls,vendor,card_details,amount\n"
        b"2026-10-18,702-KEEP-1,https://amazon.ca/orders/702-KEEP-1,Amazon.ca,Mastercard ****1234,-10.00\n"
        b'2026-10-18,702-KEEP-2,"https://amazon.ca/orders/702-KEEP-2, https://amazon.ca/orders/702-KEEP-ALT",AMZN Mktp CA,Mastercard ****1234,-20.00\n'
        b"2026-10-18,702-SKIP-PV,https://amazon.ca/orders/pv,PrimeVideo,Mastercard ****1234,-14.99\n"
        b"2026-10-18,702-SKIP-AUD,https://amazon.ca/orders/aud,Audible.ca,Mastercard ****1234,-16.95\n"
    )

    resp = client.post(
        "/api/importers/amazon_csv/run",
        headers=auth_headers,
        files={"file": ("amazon_enhanced.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["staged_count"] == 2
    assert data["skipped_duplicates"] == 0

    staged_items = data["items"]
    assert len(staged_items) == 2
    assert staged_items[0]["url"] == "https://amazon.ca/orders/702-KEEP-1"
    assert staged_items[1]["url"] == "https://amazon.ca/orders/702-KEEP-2"

    # Verify persisted in database
    st1 = db_session.query(StagedTransaction).filter_by(external_id="702-KEEP-1_2026-10-18_10.00").first()
    assert st1 is not None
    assert st1.url == "https://amazon.ca/orders/702-KEEP-1"

    st2 = db_session.query(StagedTransaction).filter_by(external_id="702-KEEP-2_2026-10-18_20.00").first()
    assert st2 is not None
    assert st2.url == "https://amazon.ca/orders/702-KEEP-2"

    # Confirm skipped rows do not exist in database
    pv_tx = db_session.query(StagedTransaction).filter(StagedTransaction.external_id.like("%702-SKIP-PV%")).first()
    assert pv_tx is None
    aud_tx = db_session.query(StagedTransaction).filter(StagedTransaction.external_id.like("%702-SKIP-AUD%")).first()
    assert aud_tx is None

    # Re-upload same CSV: verify deduplication behavior
    # Skipped rows should not count towards duplicates because they were skipped before deduplication
    resp_reup = client.post(
        "/api/importers/amazon_csv/run",
        headers=auth_headers,
        files={"file": ("amazon_enhanced.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp_reup.status_code == 200
    reup_data = resp_reup.json()
    assert reup_data["staged_count"] == 0
    assert reup_data["skipped_duplicates"] == 2
