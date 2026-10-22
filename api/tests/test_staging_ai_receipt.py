import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.staged_transaction import StagedTransaction

MOCK_ADMIN = "admin"
MOCK_PASSWORD = "admin"
MOCK_SECRET_KEY = "mock-secret-key-that-is-at-least-32-characters-long!"
MOCK_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", MOCK_ADMIN)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", MOCK_PASSWORD)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", MOCK_SECRET_KEY)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", MOCK_ALGORITHM)
    storage_dir = tmp_path / "receipts"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "RECEIPT_STORAGE_DIR", storage_dir)
    monkeypatch.setattr(settings, "AI_PROVIDER", "mock")


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


def test_parse_staged_receipt_happy_path(client, auth_headers, db_session):
    receipt_filename = "receipt_87_45.png"
    receipt_file = settings.RECEIPT_STORAGE_DIR / receipt_filename
    receipt_file.write_bytes(b"dummy image bytes for receipt parsing")

    staged_tx = StagedTransaction(
        id=uuid.uuid4(),
        source="test_source",
        status="STAGED",
        date=date(2026, 10, 15),
        description="Pending Receipt",
        total_amount=Decimal("87.45"),
        receipt_file_path=receipt_filename,
    )
    db_session.add(staged_tx)
    db_session.commit()

    response = client.post(
        f"/api/staging/{staged_tx.id}/parse-receipt",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["merchant"] == "Sample Store"
    assert data["total_amount"] == "87.45"
    assert data["description"] == "Sample Store - Office supplies"
    assert data["date"] is not None


def test_parse_staged_receipt_missing_receipt_path(client, auth_headers, db_session):
    staged_tx = StagedTransaction(
        id=uuid.uuid4(),
        source="test_source",
        status="STAGED",
        date=date(2026, 10, 15),
        description="No Receipt",
        total_amount=Decimal("15.00"),
        receipt_file_path=None,
    )
    db_session.add(staged_tx)
    db_session.commit()

    response = client.post(
        f"/api/staging/{staged_tx.id}/parse-receipt",
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "No receipt attached to staged transaction" in response.json()["detail"]


def test_parse_staged_receipt_file_missing_on_disk(client, auth_headers, db_session):
    staged_tx = StagedTransaction(
        id=uuid.uuid4(),
        source="test_source",
        status="STAGED",
        date=date(2026, 10, 15),
        description="Missing On Disk",
        total_amount=Decimal("20.00"),
        receipt_file_path="nonexistent_receipt.png",
    )
    db_session.add(staged_tx)
    db_session.commit()

    response = client.post(
        f"/api/staging/{staged_tx.id}/parse-receipt",
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Receipt file not found" in response.json()["detail"]


def test_parse_staged_receipt_nonexistent_id(client, auth_headers):
    random_id = uuid.uuid4()
    response = client.post(
        f"/api/staging/{random_id}/parse-receipt",
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert f"Staged transaction with ID '{random_id}' not found" in response.json()["detail"]


@pytest.mark.parametrize("status_val", ["ACCEPTED", "DISMISSED"])
def test_parse_staged_receipt_non_staged_status(client, auth_headers, db_session, status_val):
    receipt_filename = "receipt.png"
    receipt_file = settings.RECEIPT_STORAGE_DIR / receipt_filename
    receipt_file.write_bytes(b"dummy image bytes")

    staged_tx = StagedTransaction(
        id=uuid.uuid4(),
        source="test_source",
        status=status_val,
        date=date(2026, 10, 15),
        description="Status Check",
        total_amount=Decimal("25.00"),
        receipt_file_path=receipt_filename,
    )
    db_session.add(staged_tx)
    db_session.commit()

    response = client.post(
        f"/api/staging/{staged_tx.id}/parse-receipt",
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert f"Cannot parse receipt for staged transaction with status '{status_val}'" in response.json()["detail"]


def test_parse_staged_receipt_unsupported_mime(client, auth_headers, db_session):
    receipt_filename = "receipt.zip"
    receipt_file = settings.RECEIPT_STORAGE_DIR / receipt_filename
    receipt_file.write_bytes(b"dummy zip bytes")

    staged_tx = StagedTransaction(
        id=uuid.uuid4(),
        source="test_source",
        status="STAGED",
        date=date(2026, 10, 15),
        description="Unsupported MIME",
        total_amount=Decimal("30.00"),
        receipt_file_path=receipt_filename,
    )
    db_session.add(staged_tx)
    db_session.commit()

    response = client.post(
        f"/api/staging/{staged_tx.id}/parse-receipt",
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_parse_staged_receipt_payload_too_large(client, auth_headers, db_session, monkeypatch):
    monkeypatch.setattr(settings, "MAX_RECEIPT_FILE_SIZE", 50)
    receipt_filename = "receipt_large.png"
    receipt_file = settings.RECEIPT_STORAGE_DIR / receipt_filename
    receipt_file.write_bytes(b"x" * 51)

    staged_tx = StagedTransaction(
        id=uuid.uuid4(),
        source="test_source",
        status="STAGED",
        date=date(2026, 10, 15),
        description="Large Receipt",
        total_amount=Decimal("35.00"),
        receipt_file_path=receipt_filename,
    )
    db_session.add(staged_tx)
    db_session.commit()

    response = client.post(
        f"/api/staging/{staged_tx.id}/parse-receipt",
        headers=auth_headers,
    )
    assert response.status_code == 413
    assert "Receipt file exceeds 20MB limit" in response.json()["detail"]


def test_parse_staged_receipt_ai_runtime_error(client, auth_headers, db_session):
    receipt_filename = "receipt_timeout.jpg"
    receipt_file = settings.RECEIPT_STORAGE_DIR / receipt_filename
    receipt_file.write_bytes(b"dummy bytes")

    staged_tx = StagedTransaction(
        id=uuid.uuid4(),
        source="test_source",
        status="STAGED",
        date=date(2026, 10, 15),
        description="Timeout Receipt",
        total_amount=Decimal("40.00"),
        receipt_file_path=receipt_filename,
    )
    db_session.add(staged_tx)
    db_session.commit()

    response = client.post(
        f"/api/staging/{staged_tx.id}/parse-receipt",
        headers=auth_headers,
    )
    assert response.status_code == 503
    assert "AI provider request timed out" in response.json()["detail"]


def test_parse_staged_receipt_ai_value_error(client, auth_headers, db_session):
    receipt_filename = "receipt_corrupt.png"
    receipt_file = settings.RECEIPT_STORAGE_DIR / receipt_filename
    receipt_file.write_bytes(b"dummy bytes")

    staged_tx = StagedTransaction(
        id=uuid.uuid4(),
        source="test_source",
        status="STAGED",
        date=date(2026, 10, 15),
        description="Corrupt Receipt",
        total_amount=Decimal("45.00"),
        receipt_file_path=receipt_filename,
    )
    db_session.add(staged_tx)
    db_session.commit()

    response = client.post(
        f"/api/staging/{staged_tx.id}/parse-receipt",
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Corrupt or unreadable document" in response.json()["detail"]


def test_parse_staged_receipt_unauthenticated(client, db_session):
    staged_tx = StagedTransaction(
        id=uuid.uuid4(),
        source="test_source",
        status="STAGED",
        date=date(2026, 10, 15),
        description="Unauthenticated",
        total_amount=Decimal("50.00"),
        receipt_file_path="receipt.png",
    )
    db_session.add(staged_tx)
    db_session.commit()

    response = client.post(f"/api/staging/{staged_tx.id}/parse-receipt")
    assert response.status_code == 401
