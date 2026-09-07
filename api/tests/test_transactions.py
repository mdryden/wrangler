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


def test_create_transaction_json_success(client, auth_headers, db_session):
    company = Company(name="General Goods Ltd")
    db_session.add(company)
    db_session.commit()

    payload = {
        "company_id": str(company.id),
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
    assert data["is_approved"] is True
    assert data["receipt_file_path"] is None
    assert len(data["allocations"]) == 1
    assert data["allocations"][0]["amount"] == "125.50"
    assert data["allocations"][0]["company_id"] == str(company.id)
    assert data["allocations"][0]["is_personal"] is False
    assert data["allocations"][0]["sync_status"] == SyncStatus.PENDING


def test_create_transaction_missing_company_id(client, auth_headers):
    payload = {
        "date": "2026-09-06",
        "description": "Missing Company",
        "total_amount": "100.00",
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_create_transaction_nonexistent_company_id(client, auth_headers):
    payload = {
        "company_id": str(uuid.uuid4()),
        "date": "2026-09-06",
        "description": "Invalid Company",
        "total_amount": "100.00",
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"]


def test_create_transaction_zero_amount(client, auth_headers, db_session):
    company = Company(name="Zero Test Co")
    db_session.add(company)
    db_session.commit()

    payload = {
        "company_id": str(company.id),
        "date": "2026-09-06",
        "description": "Zero Amount Expense",
        "total_amount": "0.00",
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_create_transaction_empty_description(client, auth_headers, db_session):
    company = Company(name="Desc Test Co")
    db_session.add(company)
    db_session.commit()

    payload = {
        "company_id": str(company.id),
        "date": "2026-09-06",
        "description": "   ",
        "total_amount": "50.00",
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_create_transaction_negative_amount_refund(client, auth_headers, db_session):
    company = Company(name="Refund Co")
    db_session.add(company)
    db_session.commit()

    payload = {
        "company_id": str(company.id),
        "date": "2026-09-06",
        "description": "Monitor Return",
        "total_amount": "-75.50",
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_amount"] == "-75.50"
    assert len(data["allocations"]) == 1
    assert data["allocations"][0]["amount"] == "-75.50"
    assert data["allocations"][0]["company_id"] == str(company.id)
    assert data["allocations"][0]["is_personal"] is False
    assert data["allocations"][0]["sync_status"] == SyncStatus.PENDING


def test_create_transaction_with_valid_multi_company_splits(client, auth_headers, db_session):
    comp1 = Company(name="Enterprise A")
    comp2 = Company(name="Enterprise B")
    db_session.add_all([comp1, comp2])
    db_session.commit()

    payload = {
        "company_id": str(comp1.id),
        "date": "2026-09-06",
        "description": "Shared Bulk Order",
        "total_amount": "200.00",
        "allocations": [
            {"amount": "120.00", "company_id": str(comp1.id)},
            {"amount": "80.00", "company_id": str(comp2.id)},
        ],
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_amount"] == "200.00"
    assert len(data["allocations"]) == 2
    assert data["allocations"][0]["amount"] == "120.00"
    assert data["allocations"][0]["company_id"] == str(comp1.id)
    assert data["allocations"][0]["is_personal"] is False
    assert data["allocations"][1]["amount"] == "80.00"
    assert data["allocations"][1]["company_id"] == str(comp2.id)
    assert data["allocations"][1]["is_personal"] is False


def test_create_transaction_with_unbalanced_splits(client, auth_headers, db_session):
    company = Company(name="Unbalanced Co")
    db_session.add(company)
    db_session.commit()

    payload = {
        "company_id": str(company.id),
        "date": "2026-09-06",
        "description": "Split Mismatch",
        "total_amount": "100.00",
        "allocations": [
            {"amount": "60.00", "company_id": str(company.id)},
            {"amount": "30.00", "company_id": str(company.id)},
        ],
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert "does not equal transaction total amount" in resp.json()["detail"]


def test_create_transaction_with_split_invalid_company(client, auth_headers, db_session):
    company = Company(name="Valid Co")
    db_session.add(company)
    db_session.commit()

    payload = {
        "company_id": str(company.id),
        "date": "2026-09-06",
        "description": "Invalid Split Company",
        "total_amount": "100.00",
        "allocations": [
            {"amount": "50.00", "company_id": str(company.id)},
            {"amount": "50.00", "company_id": str(uuid.uuid4())},
        ],
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"]


def test_create_transaction_with_split_personal_rejected(client, auth_headers, db_session):
    company = Company(name="Business Only Co")
    db_session.add(company)
    db_session.commit()

    payload = {
        "company_id": str(company.id),
        "date": "2026-09-06",
        "description": "Personal Split Attempt",
        "total_amount": "100.00",
        "allocations": [
            {"amount": "50.00", "company_id": str(company.id)},
            {"amount": "50.00", "is_personal": True},
        ],
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert "business allocations" in resp.json()["detail"]


def test_create_transaction_duplicate_prevention(client, auth_headers, db_session):
    company = Company(name="Vendor Co")
    db_session.add(company)
    db_session.commit()

    payload = {
        "company_id": str(company.id),
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


def test_create_transaction_multipart_with_receipt(client, auth_headers, db_session):
    company = Company(name="Receipt Test Co")
    db_session.add(company)
    db_session.commit()

    file_bytes = b"%PDF-1.4 test receipt file contents"
    files = {"receipt": ("invoice.pdf", io.BytesIO(file_bytes), "application/pdf")}
    data = {
        "company_id": str(company.id),
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
    assert len(res_data["allocations"]) == 1
    assert res_data["allocations"][0]["amount"] == "78.25"
    assert res_data["allocations"][0]["company_id"] == str(company.id)

    # Verify retrieval
    receipt_resp = client.get(f"/api/receipts/{res_data['receipt_file_path']}", headers=auth_headers)
    assert receipt_resp.status_code == 200
    assert receipt_resp.content == file_bytes


def test_create_transaction_multipart_with_splits_json(client, auth_headers, db_session):
    comp1 = Company(name="Multipart Co A")
    comp2 = Company(name="Multipart Co B")
    db_session.add_all([comp1, comp2])
    db_session.commit()

    file_bytes = b"image bytes jpeg simulation"
    files = {"receipt": ("receipt.jpg", io.BytesIO(file_bytes), "image/jpeg")}
    import json

    splits = [
        {"amount": "60.00", "company_id": str(comp1.id)},
        {"amount": "40.00", "company_id": str(comp2.id)},
    ]
    data = {
        "company_id": str(comp1.id),
        "date": "2026-09-06",
        "description": "Split receipt multipart",
        "total_amount": "100.00",
        "allocations": json.dumps(splits),
    }
    resp = client.post("/api/transactions", data=data, files=files, headers=auth_headers)
    assert resp.status_code == 201
    res_data = resp.json()
    assert res_data["total_amount"] == "100.00"
    assert res_data["is_approved"] is True
    assert res_data["receipt_file_path"] is not None
    assert len(res_data["allocations"]) == 2
    assert res_data["allocations"][0]["amount"] == "60.00"
    assert res_data["allocations"][1]["amount"] == "40.00"


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


def test_get_transactions_filtering(client, auth_headers, db_session):
    # Seed distinct transactions
    tx1 = Transaction(
        source="bank_a",
        external_id="TX-1",
        date=date(2026, 9, 1),
        description="Office supply store",
        total_amount=Decimal("50.00"),
        is_approved=True,
    )
    tx2 = Transaction(
        source="bank_b",
        external_id="TX-2",
        date=date(2026, 9, 5),
        description="Gas station",
        total_amount=Decimal("30.00"),
        is_approved=False,
    )
    tx3 = Transaction(
        source="bank_a",
        external_id="TX-3",
        date=date(2026, 9, 10),
        description="Restaurant meal",
        total_amount=Decimal("75.00"),
        is_approved=False,
    )
    tx4 = Transaction(
        source="manual",
        external_id="TX-4",
        date=date(2026, 9, 15),
        description="Client payment",
        total_amount=Decimal("200.00"),
        is_approved=True,
    )
    db_session.add_all([tx1, tx2, tx3, tx4])
    db_session.commit()

    # Filter by source
    resp_source = client.get("/api/transactions?source=bank_a", headers=auth_headers)
    assert resp_source.status_code == 200
    data_source = resp_source.json()
    assert data_source["total"] == 2
    assert {item["external_id"] for item in data_source["items"]} == {"TX-1", "TX-3"}

    # Filter by is_approved=True
    resp_appr_true = client.get("/api/transactions?is_approved=true", headers=auth_headers)
    assert resp_appr_true.status_code == 200
    data_appr_true = resp_appr_true.json()
    assert all(item["is_approved"] is True for item in data_appr_true["items"])
    assert "TX-1" in {item["external_id"] for item in data_appr_true["items"]}
    assert "TX-4" in {item["external_id"] for item in data_appr_true["items"]}

    # Filter by is_approved=False
    resp_appr_false = client.get("/api/transactions?is_approved=false", headers=auth_headers)
    assert resp_appr_false.status_code == 200
    data_appr_false = resp_appr_false.json()
    assert all(item["is_approved"] is False for item in data_appr_false["items"])
    assert "TX-2" in {item["external_id"] for item in data_appr_false["items"]}
    assert "TX-3" in {item["external_id"] for item in data_appr_false["items"]}

    # Filter by date range (start_date and end_date)
    resp_date_range = client.get("/api/transactions?start_date=2026-09-04&end_date=2026-09-12", headers=auth_headers)
    assert resp_date_range.status_code == 200
    data_date_range = resp_date_range.json()
    assert data_date_range["total"] == 2
    assert {item["external_id"] for item in data_date_range["items"]} == {"TX-2", "TX-3"}

    # Filter by start_date only
    resp_start = client.get("/api/transactions?start_date=2026-09-10", headers=auth_headers)
    assert resp_start.status_code == 200
    data_start = resp_start.json()
    assert data_start["total"] == 2
    assert {item["external_id"] for item in data_start["items"]} == {"TX-3", "TX-4"}

    # Filter by end_date only
    resp_end = client.get("/api/transactions?end_date=2026-09-05", headers=auth_headers)
    assert resp_end.status_code == 200
    data_end = resp_end.json()
    assert data_end["total"] == 2
    assert {item["external_id"] for item in data_end["items"]} == {"TX-1", "TX-2"}

    # Combined filters: source + is_approved + date range
    resp_combo = client.get(
        "/api/transactions?source=bank_a&is_approved=false&start_date=2026-09-01&end_date=2026-09-15",
        headers=auth_headers,
    )
    assert resp_combo.status_code == 200
    data_combo = resp_combo.json()
    assert data_combo["total"] == 1
    assert data_combo["items"][0]["external_id"] == "TX-3"

    # Filter by company_id
    comp = Company(name="Acme Filtering Corp")
    db_session.add(comp)
    db_session.flush()

    alloc = Allocation(
        transaction_id=tx1.id,
        amount=Decimal("50.00"),
        is_personal=False,
        company_id=comp.id,
        sync_status=SyncStatus.PENDING,
    )
    db_session.add(alloc)
    db_session.commit()

    resp_comp = client.get(f"/api/transactions?company_id={comp.id}", headers=auth_headers)
    assert resp_comp.status_code == 200
    data_comp = resp_comp.json()
    assert data_comp["total"] == 1
    assert data_comp["items"][0]["external_id"] == "TX-1"
