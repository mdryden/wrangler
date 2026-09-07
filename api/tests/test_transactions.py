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
from models.allocation import Allocation, SyncStatus
from models.company import Company
from models.transaction import Transaction

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
    receipt_dir = tmp_path / "test_receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "RECEIPT_STORAGE_DIR", receipt_dir)


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


def test_transactions_unauthenticated_requests_blocked(client):
    random_id = uuid.uuid4()
    assert client.get("/api/transactions").status_code == 401
    assert client.post("/api/transactions", json={"date": "2026-09-06", "description": "X", "total_amount": "10.00"}).status_code == 401
    assert client.get(f"/api/transactions/{random_id}").status_code == 401
    assert client.put(f"/api/transactions/{random_id}", json={"description": "Y"}).status_code == 401
    assert client.put(f"/api/transactions/{random_id}/approve").status_code == 401
    assert client.put(f"/api/transactions/{random_id}/allocations", json=[]).status_code == 401
    assert client.delete(f"/api/transactions/{random_id}").status_code == 401
    assert client.get("/api/receipts/some_file.pdf").status_code == 401


def test_create_transaction_json_success(client, auth_headers):
    payload = {
        "date": "2026-09-06",
        "description": "Office Supplies",
        "total_amount": "125.50",
        "currency_code": "USD",
        "source": "manual",
        "external_id": "EXP-001",
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["description"] == "Office Supplies"
    assert data["total_amount"] == "125.50"
    assert data["currency_code"] == "USD"
    assert data["source"] == "manual"
    assert data["external_id"] == "EXP-001"
    assert data["is_approved"] is False
    assert data["allocations"] == []
    assert data["receipt_file_path"] is None


def test_create_transaction_duplicate_prevention(client, auth_headers):
    payload = {
        "date": "2026-09-06",
        "description": "Invoice 1",
        "total_amount": "50.00",
        "source": "vendor_a",
        "external_id": "INV-100",
    }
    resp1 = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp1.status_code == 201

    # Attempting to insert duplicate source + external_id
    resp2 = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp2.status_code == 409


def test_create_transaction_multipart_with_receipt(client, auth_headers):
    file_bytes = b"%PDF-1.4 test receipt file contents"
    files = {"receipt": ("invoice.pdf", io.BytesIO(file_bytes), "application/pdf")}
    data = {
        "date": "2026-09-06",
        "description": "Printed receipt manual entry",
        "total_amount": "78.25",
        "currency_code": "USD",
        "source": "manual",
        "is_approved": "true",
    }
    resp = client.post("/api/transactions", data=data, files=files, headers=auth_headers)
    assert resp.status_code == 201
    res_data = resp.json()
    assert res_data["description"] == "Printed receipt manual entry"
    assert res_data["total_amount"] == "78.25"
    assert res_data["is_approved"] is True
    assert res_data["receipt_file_path"] is not None
    assert res_data["receipt_file_path"].endswith("invoice.pdf")

    # Verify retrieval
    receipt_resp = client.get(f"/api/receipts/{res_data['receipt_file_path']}", headers=auth_headers)
    assert receipt_resp.status_code == 200
    assert receipt_resp.content == file_bytes


def test_get_transactions_pagination(client, auth_headers, db_session):
    # Seed 15 transactions
    for i in range(15):
        tx = Transaction(
            source="manual",
            external_id=f"SEED-{i:02d}",
            date=date(2026, 9, 1 + (i % 5)),
            description=f"Transaction {i:02d}",
            total_amount=Decimal(f"{(i + 1) * 10}.00"),
        )
        db_session.add(tx)
    db_session.commit()

    # Page 1, size 5
    resp = client.get("/api/transactions?page=1&page_size=5", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 15
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert data["total_pages"] == 3
    assert len(data["items"]) == 5

    # Page 3, size 5
    resp3 = client.get("/api/transactions?page=3&page_size=5", headers=auth_headers)
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert len(data3["items"]) == 5

    # Quasar alias parameters
    resp_quasar = client.get("/api/transactions?page=2&rowsPerPage=4&sortBy=total_amount&order=asc", headers=auth_headers)
    assert resp_quasar.status_code == 200
    data_q = resp_quasar.json()
    assert data_q["page_size"] == 4
    assert len(data_q["items"]) == 4
    assert Decimal(data_q["items"][0]["total_amount"]) < Decimal(data_q["items"][-1]["total_amount"])


def test_update_transaction_metadata(client, auth_headers, db_session):
    tx = Transaction(
        source="manual",
        external_id="UPDATE-01",
        date=date(2026, 9, 6),
        description="Original description",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.commit()

    update_payload = {
        "description": "Updated description",
        "total_amount": "120.00",
    }
    resp = client.put(f"/api/transactions/{tx.id}", json=update_payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "Updated description"
    assert data["total_amount"] == "120.00"
    assert data["source"] == "manual"


def test_approve_transaction(client, auth_headers, db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="To approve",
        total_amount=Decimal("50.00"),
        is_approved=False,
    )
    db_session.add(tx)
    db_session.commit()

    # Toggle to True
    resp1 = client.put(f"/api/transactions/{tx.id}/approve", headers=auth_headers)
    assert resp1.status_code == 200
    assert resp1.json()["is_approved"] is True

    # Toggle to False
    resp2 = client.put(f"/api/transactions/{tx.id}/approve", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["is_approved"] is False

    # Explicit set to True
    resp3 = client.put(f"/api/transactions/{tx.id}/approve", json={"is_approved": True}, headers=auth_headers)
    assert resp3.status_code == 200
    assert resp3.json()["is_approved"] is True


def test_update_allocations_success(client, auth_headers, db_session):
    company = Company(name="Test Co")
    db_session.add(company)
    db_session.commit()

    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Split expense",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.commit()

    allocations_payload = [
        {
            "amount": "40.00",
            "is_personal": True,
            "sync_status": "PENDING",
        },
        {
            "amount": "60.00",
            "is_personal": False,
            "company_id": str(company.id),
            "sync_status": "PENDING",
        },
    ]

    resp = client.put(f"/api/transactions/{tx.id}/allocations", json=allocations_payload, headers=auth_headers)
    assert resp.status_code == 200
    allocations = resp.json()
    assert len(allocations) == 2
    assert allocations[0]["is_personal"] is True
    assert allocations[0]["company_id"] is None
    assert allocations[1]["is_personal"] is False
    assert allocations[1]["company_id"] == str(company.id)


def test_update_allocations_validation_errors(client, auth_headers, db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Split expense",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.commit()

    bad_company_id = uuid.uuid4()
    bad_payload = [
        {
            "amount": "100.00",
            "is_personal": False,
            "company_id": str(bad_company_id),
        }
    ]
    resp = client.put(f"/api/transactions/{tx.id}/allocations", json=bad_payload, headers=auth_headers)
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()


def test_immutability_validation_on_synced_allocations(client, auth_headers, db_session):
    # 5.6 Enforce immutability validation on allocations (HTTP 400 if any allocation is SYNCED)
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Synced transaction",
        total_amount=Decimal("200.00"),
    )
    db_session.add(tx)
    db_session.commit()

    # Add a SYNCED allocation
    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("200.00"),
        is_personal=False,
        sync_status=SyncStatus.SYNCED,
    )
    db_session.add(alloc)
    db_session.commit()

    # Attempt to update allocations must fail with HTTP 400
    alloc_payload = [{"amount": "200.00", "is_personal": True}]
    resp_alloc = client.put(f"/api/transactions/{tx.id}/allocations", json=alloc_payload, headers=auth_headers)
    assert resp_alloc.status_code == 400
    assert "SYNCED" in resp_alloc.json()["detail"]

    # Attempt to update transaction metadata must fail with HTTP 400
    resp_meta = client.put(f"/api/transactions/{tx.id}", json={"description": "Changed"}, headers=auth_headers)
    assert resp_meta.status_code == 400
    assert "SYNCED" in resp_meta.json()["detail"]

    # Attempt to delete transaction must fail with HTTP 400
    resp_del = client.delete(f"/api/transactions/{tx.id}", headers=auth_headers)
    assert resp_del.status_code == 400
    assert "SYNCED" in resp_del.json()["detail"]


def test_upload_and_retrieve_receipt(client, auth_headers, db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Receipt upload test",
        total_amount=Decimal("35.00"),
    )
    db_session.add(tx)
    db_session.commit()

    receipt_content = b"PDF receipt sample bytes"
    files = {"file": ("receipt.pdf", io.BytesIO(receipt_content), "application/pdf")}
    upload_resp = client.post(f"/api/transactions/{tx.id}/receipt", files=files, headers=auth_headers)
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert data["receipt_file_path"] is not None

    # Retrieve receipt
    get_resp = client.get(f"/api/receipts/{data['receipt_file_path']}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.content == receipt_content


def test_receipt_path_traversal_blocked(client, auth_headers):
    # Attempting directory traversal
    resp = client.get("/api/receipts/../../etc/passwd", headers=auth_headers)
    assert resp.status_code in (400, 404)

    # Non-existent file
    resp404 = client.get("/api/receipts/non_existent_file.pdf", headers=auth_headers)
    assert resp404.status_code == 404
