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
from models.allocation import Allocation
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
    assert client.put(f"/api/transactions/{random_id}/allocations", json=[]).status_code == 401
    assert client.delete(f"/api/transactions/{random_id}").status_code == 401
    assert client.get("/api/receipts/some_file.pdf").status_code == 401


def test_create_transaction_json_success(client, auth_headers, db_session):
    company = Company(name="General Goods Ltd")
    db_session.add(company)
    db_session.commit()

    payload = {
        "date": "2026-09-06",
        "description": "Office Supplies",
        "total_amount": "125.50",
        "source": "manual",
        "external_id": "EXP-001",
        "allocations": [
            {"amount": "125.50", "company_id": str(company.id)},
        ],
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["description"] == "Office Supplies"
    assert data["total_amount"] == "125.50"
    assert data["source"] == "manual"
    assert data["external_id"] == "EXP-001"
    assert data["receipt_file_path"] is None
    assert len(data["allocations"]) == 1
    assert data["allocations"][0]["amount"] == "125.50"
    assert data["allocations"][0]["company_id"] == str(company.id)
    assert data["allocations"][0]["is_personal"] is False
    assert data["allocations"][0]["is_locked"] is False


def test_create_transaction_default_allocation_via_company_id(client, auth_headers, db_session):
    company = Company(name="Default Alloc Co")
    db_session.add(company)
    db_session.commit()

    payload = {
        "date": "2026-09-06",
        "description": "Single Company Expense",
        "total_amount": "85.00",
        "company_id": str(company.id),
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_amount"] == "85.00"
    assert len(data["allocations"]) == 1
    assert data["allocations"][0]["amount"] == "85.00"
    assert data["allocations"][0]["company_id"] == str(company.id)
    assert data["allocations"][0]["is_personal"] is False
    assert data["allocations"][0]["is_locked"] is False


def test_create_transaction_missing_allocations(client, auth_headers):
    payload = {
        "date": "2026-09-06",
        "description": "Missing Allocations",
        "total_amount": "100.00",
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_create_transaction_nonexistent_company_id(client, auth_headers):
    payload = {
        "date": "2026-09-06",
        "description": "Invalid Company",
        "total_amount": "100.00",
        "allocations": [
            {"amount": "100.00", "company_id": str(uuid.uuid4())},
        ],
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"]


def test_create_transaction_zero_amount(client, auth_headers, db_session):
    company = Company(name="Zero Test Co")
    db_session.add(company)
    db_session.commit()

    payload = {
        "date": "2026-09-06",
        "description": "Zero Amount Expense",
        "total_amount": "0.00",
        "allocations": [
            {"amount": "0.00", "company_id": str(company.id)},
        ],
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_create_transaction_empty_description(client, auth_headers, db_session):
    company = Company(name="Desc Test Co")
    db_session.add(company)
    db_session.commit()

    payload = {
        "date": "2026-09-06",
        "description": "   ",
        "total_amount": "50.00",
        "allocations": [
            {"amount": "50.00", "company_id": str(company.id)},
        ],
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_create_transaction_negative_amount_refund(client, auth_headers, db_session):
    company = Company(name="Refund Co")
    db_session.add(company)
    db_session.commit()

    payload = {
        "date": "2026-09-06",
        "description": "Monitor Return",
        "total_amount": "-75.50",
        "allocations": [
            {"amount": "-75.50", "company_id": str(company.id)},
        ],
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_amount"] == "-75.50"
    assert len(data["allocations"]) == 1
    assert data["allocations"][0]["amount"] == "-75.50"
    assert data["allocations"][0]["company_id"] == str(company.id)
    assert data["allocations"][0]["is_personal"] is False
    assert data["allocations"][0]["is_locked"] is False


def test_create_transaction_with_valid_multi_company_splits(client, auth_headers, db_session):
    comp1 = Company(name="Enterprise A")
    comp2 = Company(name="Enterprise B")
    db_session.add_all([comp1, comp2])
    db_session.commit()

    payload = {
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
        "date": "2026-09-06",
        "description": "Invoice 1",
        "total_amount": "50.00",
        "source": "vendor_a",
        "external_id": "INV-100",
        "allocations": [
            {"amount": "50.00", "company_id": str(company.id)},
        ],
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
    import json

    data = {
        "date": "2026-09-06",
        "description": "Printed receipt manual entry",
        "total_amount": "78.25",
        "source": "manual",
        "allocations": json.dumps([{"amount": "78.25", "company_id": str(company.id)}]),
    }
    resp = client.post("/api/transactions", data=data, files=files, headers=auth_headers)
    assert resp.status_code == 201
    res_data = resp.json()
    assert res_data["description"] == "Printed receipt manual entry"
    assert res_data["total_amount"] == "78.25"
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
        "date": "2026-09-06",
        "description": "Split receipt multipart",
        "total_amount": "100.00",
        "allocations": json.dumps(splits),
    }
    resp = client.post("/api/transactions", data=data, files=files, headers=auth_headers)
    assert resp.status_code == 201
    res_data = resp.json()
    assert res_data["total_amount"] == "100.00"
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


def test_update_allocations_success(client, auth_headers, db_session):
    comp1 = Company(name="Test Co A")
    comp2 = Company(name="Test Co B")
    db_session.add_all([comp1, comp2])
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
            "is_personal": False,
            "company_id": str(comp1.id),
            "is_locked": False,
        },
        {
            "amount": "60.00",
            "is_personal": False,
            "company_id": str(comp2.id),
            "is_locked": False,
        },
    ]

    resp = client.put(f"/api/transactions/{tx.id}/allocations", json=allocations_payload, headers=auth_headers)
    assert resp.status_code == 200
    allocations = resp.json()
    assert len(allocations) == 2
    assert allocations[0]["is_personal"] is False
    assert allocations[0]["company_id"] == str(comp1.id)
    assert allocations[1]["is_personal"] is False
    assert allocations[1]["company_id"] == str(comp2.id)

    # Single personal allocation clears company_id to None
    personal_payload = [
        {
            "amount": "100.00",
            "is_personal": True,
            "company_id": str(comp1.id),
            "is_locked": False,
        }
    ]
    resp_personal = client.put(f"/api/transactions/{tx.id}/allocations", json=personal_payload, headers=auth_headers)
    assert resp_personal.status_code == 200
    p_allocs = resp_personal.json()
    assert len(p_allocs) == 1
    assert p_allocs[0]["is_personal"] is True
    assert p_allocs[0]["company_id"] is None


def test_update_allocations_validation_errors(client, auth_headers, db_session):
    comp = Company(name="Valid Split Co")
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Split expense",
        total_amount=Decimal("100.00"),
    )
    db_session.add_all([comp, tx])
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

    # Reject personal split when len(allocations) > 1
    mixed_payload = [
        {"amount": "40.00", "is_personal": True},
        {"amount": "60.00", "is_personal": False, "company_id": str(comp.id)},
    ]
    resp_mixed = client.put(f"/api/transactions/{tx.id}/allocations", json=mixed_payload, headers=auth_headers)
    assert resp_mixed.status_code == 400
    assert "Only business transactions can be split" in resp_mixed.json()["detail"]

    # Reject unbalanced splits
    unbalanced_payload = [
        {"amount": "40.00", "is_personal": False, "company_id": str(comp.id)},
    ]
    resp_unbalanced = client.put(f"/api/transactions/{tx.id}/allocations", json=unbalanced_payload, headers=auth_headers)
    assert resp_unbalanced.status_code == 400
    assert "does not equal transaction total amount" in resp_unbalanced.json()["detail"]


def test_immutability_validation_on_synced_allocations(client, auth_headers, db_session):
    # Full lock validation: HTTP 400 if all allocations are locked
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Locked transaction",
        total_amount=Decimal("200.00"),
    )
    db_session.add(tx)
    db_session.commit()

    # Add a locked allocation
    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("200.00"),
        is_personal=False,
        is_locked=True,
    )
    db_session.add(alloc)
    db_session.commit()

    # Attempt to update allocations must fail with HTTP 400
    alloc_payload = [{"amount": "200.00", "is_personal": True}]
    resp_alloc = client.put(f"/api/transactions/{tx.id}/allocations", json=alloc_payload, headers=auth_headers)
    assert resp_alloc.status_code == 400
    assert "all allocations are locked" in resp_alloc.json()["detail"].lower()

    # Attempt to update transaction metadata must fail with HTTP 400
    resp_meta = client.put(f"/api/transactions/{tx.id}", json={"description": "Changed"}, headers=auth_headers)
    assert resp_meta.status_code == 400
    assert "all allocations are locked" in resp_meta.json()["detail"].lower()

    # Attempt to delete transaction must fail with HTTP 400
    resp_del = client.delete(f"/api/transactions/{tx.id}", headers=auth_headers)
    assert resp_del.status_code == 400
    assert "locked" in resp_del.json()["detail"].lower()


def test_partial_lock_and_unified_update_transaction(client, auth_headers, db_session):
    comp_a = Company(name="Partial Lock Co A")
    comp_b = Company(name="Partial Lock Co B")
    comp_c = Company(name="Partial Lock Co C")
    db_session.add_all([comp_a, comp_b, comp_c])
    db_session.flush()

    tx = Transaction(
        source="manual",
        date=date(2026, 9, 10),
        description="Original Split Expense",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.flush()

    alloc_locked = Allocation(
        transaction_id=tx.id,
        company_id=comp_a.id,
        amount=Decimal("40.00"),
        is_personal=False,
        is_locked=True,
    )
    alloc_unlocked = Allocation(
        transaction_id=tx.id,
        company_id=comp_b.id,
        amount=Decimal("60.00"),
        is_personal=False,
        is_locked=False,
    )
    db_session.add_all([alloc_locked, alloc_unlocked])
    db_session.commit()

    # 1. Modifying date or description while partially locked fails with 400
    resp_desc = client.put(f"/api/transactions/{tx.id}", json={"description": "New Desc"}, headers=auth_headers)
    assert resp_desc.status_code == 400
    assert "locked" in resp_desc.json()["detail"].lower()

    resp_date = client.put(f"/api/transactions/{tx.id}", json={"date": "2026-09-11"}, headers=auth_headers)
    assert resp_date.status_code == 400
    assert "locked" in resp_date.json()["detail"].lower()

    # 2. Modifying or removing the locked allocation fails with 400
    bad_preserve_payload = {
        "allocations": [
            {
                "id": str(alloc_locked.id),
                "company_id": str(comp_a.id),
                "amount": "50.00",
                "is_personal": False,
                "is_locked": True,
            },
            {
                "id": str(alloc_unlocked.id),
                "company_id": str(comp_b.id),
                "amount": "50.00",
                "is_personal": False,
                "is_locked": False,
            },
        ]
    }
    resp_bad_lock = client.put(f"/api/transactions/{tx.id}", json=bad_preserve_payload, headers=auth_headers)
    assert resp_bad_lock.status_code == 400
    assert "locked" in resp_bad_lock.json()["detail"].lower()

    # 3. Preserving the locked allocation and splitting the unlocked allocation across comp_b and comp_c succeeds
    valid_partial_payload = {
        "allocations": [
            {
                "id": str(alloc_locked.id),
                "company_id": str(comp_a.id),
                "amount": "40.00",
                "is_personal": False,
                "is_locked": True,
            },
            {
                "id": str(alloc_unlocked.id),
                "company_id": str(comp_b.id),
                "amount": "25.00",
                "is_personal": False,
                "is_locked": False,
            },
            {
                "company_id": str(comp_c.id),
                "amount": "35.00",
                "is_personal": False,
                "is_locked": False,
            },
        ]
    }
    resp_ok = client.put(f"/api/transactions/{tx.id}", json=valid_partial_payload, headers=auth_headers)
    assert resp_ok.status_code == 200
    ok_data = resp_ok.json()
    assert len(ok_data["allocations"]) == 3

    # 4. Multipart receipt upload and removal via PUT /api/transactions/{id} works even when all allocations are locked
    for a in db_session.get(Transaction, tx.id).allocations:
        a.is_locked = True
    db_session.commit()

    receipt_bytes = b"%PDF-1.4 unified edit receipt"
    files = {"file": ("unified.pdf", io.BytesIO(receipt_bytes), "application/pdf")}
    resp_upload = client.put(f"/api/transactions/{tx.id}", data={}, files=files, headers=auth_headers)
    assert resp_upload.status_code == 200
    saved_receipt = resp_upload.json()["receipt_file_path"]
    assert saved_receipt is not None
    assert (settings.RECEIPT_STORAGE_DIR / saved_receipt).exists()

    resp_remove = client.put(f"/api/transactions/{tx.id}", json={"remove_receipt": True}, headers=auth_headers)
    assert resp_remove.status_code == 200
    assert resp_remove.json()["receipt_file_path"] is None
    assert not (settings.RECEIPT_STORAGE_DIR / saved_receipt).exists()


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

    # Retrieve receipt with inline disposition and detected PDF media type
    get_resp = client.get(f"/api/receipts/{data['receipt_file_path']}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.content == receipt_content
    assert "application/pdf" in get_resp.headers["content-type"]
    assert "inline" in get_resp.headers["content-disposition"]


def test_receipt_replacement_cleanup_and_deletion_when_locked(client, auth_headers, db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Locked receipt test",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.flush()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("100.00"),
        is_personal=True,
        is_locked=True,
    )
    db_session.add(alloc)
    db_session.commit()

    # 1. Upload PNG receipt while transaction is locked
    png_bytes = b"\x89PNG\r\n\x1a\npng_content"
    files1 = {"file": ("first.png", io.BytesIO(png_bytes), "image/png")}
    resp1 = client.post(f"/api/transactions/{tx.id}/receipt", files=files1, headers=auth_headers)
    assert resp1.status_code == 200
    first_path = resp1.json()["receipt_file_path"]
    assert (settings.RECEIPT_STORAGE_DIR / first_path).exists()

    get_png = client.get(f"/api/receipts/{first_path}", headers=auth_headers)
    assert get_png.status_code == 200
    assert "image/png" in get_png.headers["content-type"]
    assert "inline" in get_png.headers["content-disposition"]

    # 2. Replace with JPEG receipt while locked -> old PNG must be deleted from disk
    jpg_bytes = b"\xff\xd8\xff\xe0jpeg_content"
    files2 = {"file": ("second.jpg", io.BytesIO(jpg_bytes), "image/jpeg")}
    resp2 = client.post(f"/api/transactions/{tx.id}/receipt", files=files2, headers=auth_headers)
    assert resp2.status_code == 200
    second_path = resp2.json()["receipt_file_path"]
    assert second_path != first_path
    assert not (settings.RECEIPT_STORAGE_DIR / first_path).exists()
    assert (settings.RECEIPT_STORAGE_DIR / second_path).exists()

    get_jpg = client.get(f"/api/receipts/{second_path}", headers=auth_headers)
    assert get_jpg.status_code == 200
    assert "image/jpeg" in get_jpg.headers["content-type"]
    assert "inline" in get_jpg.headers["content-disposition"]

    # 3. Delete receipt while transaction is locked -> file removed from disk & path set to None
    del_resp = client.delete(f"/api/transactions/{tx.id}/receipt", headers=auth_headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["receipt_file_path"] is None
    assert not (settings.RECEIPT_STORAGE_DIR / second_path).exists()

    # 4. Delete receipt on non-existent transaction returns 404
    not_found_resp = client.delete(f"/api/transactions/{uuid.uuid4()}/receipt", headers=auth_headers)
    assert not_found_resp.status_code == 404


def test_delete_transaction_lock_guard_and_receipt_cleanup(client, auth_headers, db_session):
    comp1 = Company(name="Del Co 1")
    comp2 = Company(name="Del Co 2")
    db_session.add_all([comp1, comp2])
    db_session.flush()

    tx = Transaction(
        source="manual",
        date=date(2026, 9, 12),
        description="Delete with receipt",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.flush()

    a1 = Allocation(transaction_id=tx.id, company_id=comp1.id, amount=Decimal("50.00"), is_personal=False, is_locked=True)
    a2 = Allocation(transaction_id=tx.id, company_id=comp2.id, amount=Decimal("50.00"), is_personal=False, is_locked=False)
    db_session.add_all([a1, a2])
    db_session.commit()

    # Upload a receipt file
    files = {"file": ("to_delete.pdf", io.BytesIO(b"PDF content"), "application/pdf")}
    up_resp = client.post(f"/api/transactions/{tx.id}/receipt", files=files, headers=auth_headers)
    assert up_resp.status_code == 200
    receipt_path = up_resp.json()["receipt_file_path"]
    assert (settings.RECEIPT_STORAGE_DIR / receipt_path).exists()

    # Partially locked transaction cannot be deleted
    blocked_del = client.delete(f"/api/transactions/{tx.id}", headers=auth_headers)
    assert blocked_del.status_code == 400
    assert "Cannot delete transaction: transaction contains locked allocations" in blocked_del.json()["detail"]
    assert (settings.RECEIPT_STORAGE_DIR / receipt_path).exists()

    # Unlock allocation -> deletion succeeds and cleans up receipt file
    a1.is_locked = False
    db_session.commit()

    ok_del = client.delete(f"/api/transactions/{tx.id}", headers=auth_headers)
    assert ok_del.status_code == 204
    assert not (settings.RECEIPT_STORAGE_DIR / receipt_path).exists()
    assert db_session.get(Transaction, tx.id) is None


def test_update_transaction_lock_endpoint(client, auth_headers, db_session):
    comp1 = Company(name="Tx Lock Co 1")
    comp2 = Company(name="Tx Lock Co 2")
    db_session.add_all([comp1, comp2])
    db_session.flush()

    tx = Transaction(
        source="manual",
        date=date(2026, 9, 14),
        description="Tx Lock Toggle",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.flush()

    a1 = Allocation(transaction_id=tx.id, company_id=comp1.id, amount=Decimal("60.00"), is_personal=False, is_locked=False)
    a2 = Allocation(transaction_id=tx.id, company_id=comp2.id, amount=Decimal("40.00"), is_personal=False, is_locked=True)
    db_session.add_all([a1, a2])
    db_session.commit()

    # Lock all allocations on transaction
    lock_resp = client.put(f"/api/transactions/{tx.id}/lock", json={"is_locked": True}, headers=auth_headers)
    assert lock_resp.status_code == 200
    assert all(a["is_locked"] is True for a in lock_resp.json()["allocations"])

    # Unlock all allocations on transaction
    unlock_resp = client.put(f"/api/transactions/{tx.id}/lock", json={"is_locked": False}, headers=auth_headers)
    assert unlock_resp.status_code == 200
    assert all(a["is_locked"] is False for a in unlock_resp.json()["allocations"])

    # Non-existent transaction returns 404
    not_found = client.put(f"/api/transactions/{uuid.uuid4()}/lock", json={"is_locked": True}, headers=auth_headers)
    assert not_found.status_code == 404


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
    )
    tx2 = Transaction(
        source="bank_b",
        external_id="TX-2",
        date=date(2026, 9, 5),
        description="Gas station",
        total_amount=Decimal("30.00"),
    )
    tx3 = Transaction(
        source="bank_a",
        external_id="TX-3",
        date=date(2026, 9, 10),
        description="Restaurant meal",
        total_amount=Decimal("75.00"),
    )
    tx4 = Transaction(
        source="manual",
        external_id="TX-4",
        date=date(2026, 9, 15),
        description="Client payment",
        total_amount=Decimal("200.00"),
    )
    db_session.add_all([tx1, tx2, tx3, tx4])
    db_session.commit()

    # Filter by source
    resp_source = client.get("/api/transactions?source=bank_a", headers=auth_headers)
    assert resp_source.status_code == 200
    data_source = resp_source.json()
    assert data_source["total"] == 2
    assert {item["external_id"] for item in data_source["items"]} == {"TX-1", "TX-3"}

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

    # Combined filters: source + date range
    resp_combo = client.get(
        "/api/transactions?source=bank_a&start_date=2026-09-05&end_date=2026-09-15",
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
        is_locked=False,
    )
    db_session.add(alloc)
    db_session.commit()

    resp_comp = client.get(f"/api/transactions?company_id={comp.id}", headers=auth_headers)
    assert resp_comp.status_code == 200
    data_comp = resp_comp.json()
    assert data_comp["total"] == 1
    assert data_comp["items"][0]["external_id"] == "TX-1"

    # Add a locked allocation on tx2 for the same company and verify include_locked=false vs true
    alloc_locked = Allocation(
        transaction_id=tx2.id,
        amount=Decimal("30.00"),
        is_personal=False,
        company_id=comp.id,
        is_locked=True,
    )
    db_session.add(alloc_locked)
    db_session.commit()

    resp_unlocked_only = client.get(
        f"/api/transactions?company_id={comp.id}&include_locked=false",
        headers=auth_headers,
    )
    assert resp_unlocked_only.status_code == 200
    data_unlocked_only = resp_unlocked_only.json()
    assert data_unlocked_only["total"] == 1
    assert data_unlocked_only["items"][0]["external_id"] == "TX-1"

    resp_include_locked = client.get(
        f"/api/transactions?company_id={comp.id}&include_locked=true",
        headers=auth_headers,
    )
    assert resp_include_locked.status_code == 200
    data_include_locked = resp_include_locked.json()
    assert data_include_locked["total"] == 2
    assert {item["external_id"] for item in data_include_locked["items"]} == {"TX-1", "TX-2"}

    # Filter by specific transaction_id (for deep-linking from Export Manager to Ledger)
    resp_tx_id = client.get(f"/api/transactions?transaction_id={tx3.id}", headers=auth_headers)
    assert resp_tx_id.status_code == 200
    data_tx_id = resp_tx_id.json()
    assert data_tx_id["total"] == 1
    assert data_tx_id["items"][0]["id"] == str(tx3.id)
