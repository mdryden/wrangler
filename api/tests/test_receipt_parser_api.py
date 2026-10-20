import hashlib
from datetime import timedelta
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
    monkeypatch.setattr(settings, "RECEIPT_STORAGE_DIR", tmp_path / "receipts")
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


def test_parse_receipt_valid_image(client, auth_headers):
    file_content = b"fake-receipt-image-content"
    response = client.post(
        "/api/receipts/parse",
        headers=auth_headers,
        files={"file": ("receipt_87_45.png", file_content, "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["merchant"] == "Sample Store"
    assert data["total_amount"] == "87.45"
    assert data["description"] == "Sample Store - Office supplies"
    assert data["date"] is not None


def test_parse_receipt_unsupported_mime_type(client, auth_headers):
    response = client.post(
        "/api/receipts/parse",
        headers=auth_headers,
        files={"file": ("archive.zip", b"fakezip", "application/zip")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_parse_receipt_exceeds_max_file_size(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "MAX_RECEIPT_FILE_SIZE", 100)
    large_content = b"x" * 101
    response = client.post(
        "/api/receipts/parse",
        headers=auth_headers,
        files={"file": ("receipt.png", large_content, "image/png")},
    )
    assert response.status_code == 413
    assert "Receipt file exceeds 20MB limit" in response.json()["detail"]


def test_parse_receipt_upstream_provider_error(client, auth_headers, monkeypatch):
    # Simulating upstream provider failure via timeout filename in mock provider
    response = client.post(
        "/api/receipts/parse",
        headers=auth_headers,
        files={"file": ("receipt_timeout.jpg", b"content", "image/jpeg")},
    )
    assert response.status_code == 503
    assert "AI provider request timed out" in response.json()["detail"]

    # Simulating missing OpenAI API key
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    response_openai = client.post(
        "/api/receipts/parse",
        headers=auth_headers,
        files={"file": ("receipt_test.png", b"content", "image/png")},
    )
    assert response_openai.status_code == 503
    assert "OPENAI_API_KEY is not configured" in response_openai.json()["detail"]


def test_importer_single_file_staging(client, auth_headers, db_session):
    file_bytes = b"sample_jpg_bytes_for_staging"
    filename = "receipt_87_45.jpg"
    expected_ext_id = f"sha256:{hashlib.sha256(file_bytes).hexdigest()}"

    response = client.post(
        "/api/importers/receipt_parser/run",
        headers=auth_headers,
        files=[("files", (filename, file_bytes, "image/jpeg"))],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["importer_id"] == "receipt_parser"
    assert data["total_parsed"] == 1
    assert data["staged_count"] == 1
    assert data["skipped_duplicates"] == 0
    assert data["failed_files"] == []
    assert len(data["items"]) == 1

    staged_item = data["items"][0]
    assert staged_item["external_id"] == expected_ext_id
    assert staged_item["total_amount"] == "87.45"
    assert staged_item["description"] == "Sample Store - Office supplies"
    assert staged_item["receipt_file_path"] is not None

    # Verify physical file existence in storage dir
    receipt_path = settings.RECEIPT_STORAGE_DIR / staged_item["receipt_file_path"]
    assert receipt_path.exists()
    assert receipt_path.read_bytes() == file_bytes

    # Verify database record
    db_record = db_session.query(StagedTransaction).filter(StagedTransaction.external_id == expected_ext_id).first()
    assert db_record is not None
    assert db_record.source == "receipt_parser"
    assert db_record.total_amount == Decimal("87.45")


def test_importer_multi_file_staging_concurrency(client, auth_headers, db_session):
    file1_bytes = b"first_receipt_content"
    file2_bytes = b"second_receipt_content"

    response = client.post(
        "/api/importers/receipt_parser/run",
        headers=auth_headers,
        files=[
            ("files", ("receipt_15_25.png", file1_bytes, "image/png")),
            ("files", ("receipt_40_50.png", file2_bytes, "image/png")),
        ],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_parsed"] == 2
    assert data["staged_count"] == 2
    assert data["skipped_duplicates"] == 0
    assert data["failed_files"] == []
    assert len(data["items"]) == 2


def test_importer_pre_ai_deduplication(client, auth_headers, db_session):
    file_bytes = b"dedup_test_receipt"
    filename = "receipt_50_00.png"

    # First import
    res1 = client.post(
        "/api/importers/receipt_parser/run",
        headers=auth_headers,
        files=[("files", (filename, file_bytes, "image/png"))],
    )
    assert res1.status_code == 200
    assert res1.json()["staged_count"] == 1
    assert res1.json()["skipped_duplicates"] == 0

    # Second import with identical file
    res2 = client.post(
        "/api/importers/receipt_parser/run",
        headers=auth_headers,
        files=[("files", (filename, file_bytes, "image/png"))],
    )
    assert res2.status_code == 200
    assert res2.json()["staged_count"] == 0
    assert res2.json()["skipped_duplicates"] == 1
    assert res2.json()["total_parsed"] == 0

    # Batch with internal duplicates
    file_batch_bytes = b"unique_batch_item"
    res3 = client.post(
        "/api/importers/receipt_parser/run",
        headers=auth_headers,
        files=[
            ("files", ("receipt_first.png", file_batch_bytes, "image/png")),
            ("files", ("receipt_second.png", file_batch_bytes, "image/png")),
        ],
    )
    assert res3.status_code == 200
    assert res3.json()["staged_count"] == 1
    assert res3.json()["skipped_duplicates"] == 1


def test_importer_resilient_batch_import(client, auth_headers):
    valid_bytes = b"valid_receipt_bytes"
    corrupt_bytes = b"corrupt_receipt_bytes"

    response = client.post(
        "/api/importers/receipt_parser/run",
        headers=auth_headers,
        files=[
            ("files", ("receipt_valid_99_00.jpg", valid_bytes, "image/jpeg")),
            ("files", ("receipt_corrupt.jpg", corrupt_bytes, "image/jpeg")),
        ],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["staged_count"] == 1
    assert data["total_parsed"] == 1
    assert len(data["failed_files"]) == 1
    assert "receipt_corrupt.jpg: Corrupt or unreadable document" in data["failed_files"][0]


def test_importer_incomplete_receipt_extraction(client, auth_headers, db_session):
    file_bytes = b"missing_total_receipt"
    response = client.post(
        "/api/importers/receipt_parser/run",
        headers=auth_headers,
        files=[("files", ("receipt_missing_total.png", file_bytes, "image/png"))],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["staged_count"] == 1
    staged_item = data["items"][0]
    assert staged_item["total_amount"] is None
    assert staged_item["is_ready"] is False


def test_importer_file_validation_errors(client, auth_headers, monkeypatch):
    # Missing files in multipart form
    res_empty = client.post(
        "/api/importers/receipt_parser/run",
        headers=auth_headers,
        files={"other_field": ("empty.png", b"", "image/png")},
    )
    assert res_empty.status_code == 400

    # Unsupported file extension
    res_unsupported = client.post(
        "/api/importers/receipt_parser/run",
        headers=auth_headers,
        files=[("files", ("receipt.txt", b"text", "text/plain"))],
    )
    assert res_unsupported.status_code == 400
    assert "Unsupported file type" in res_unsupported.json()["detail"]

    # File size limit exceeded
    monkeypatch.setattr(settings, "MAX_RECEIPT_FILE_SIZE", 50)
    res_toolarge = client.post(
        "/api/importers/receipt_parser/run",
        headers=auth_headers,
        files=[("files", ("receipt_large.png", b"x" * 51, "image/png"))],
    )
    assert res_toolarge.status_code == 413
    assert "exceeds maximum allowed size of 20MB" in res_toolarge.json()["detail"]
