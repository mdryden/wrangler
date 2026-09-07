import io
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.allocation import SyncStatus
from models.company import Company

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
    receipt_dir = tmp_path / "integration_receipts"
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


def test_transaction_allocation_receipt_lifecycle_flow(client, auth_headers, db_session):
    """End-to-end integration flow testing transaction creation, pagination, approval, receipts, split allocations, and immutability locking."""
    # 1. Set up company
    company = Company(name="Acme Consulting LLC")
    db_session.add(company)
    db_session.commit()

    # 2. Create a manual transaction
    tx_payload = {
        "company_id": str(company.id),
        "date": "2026-09-06",
        "description": "Hardware & Office Setup",
        "total_amount": "250.00",
        "currency_code": "USD",
        "source": "manual",
        "external_id": "INT-TX-001",
    }
    tx_resp = client.post("/api/transactions", json=tx_payload, headers=auth_headers)
    assert tx_resp.status_code == 201
    tx_data = tx_resp.json()
    tx_id = tx_data["id"]
    assert tx_data["description"] == "Hardware & Office Setup"
    assert len(tx_data["allocations"]) == 1
    assert tx_data["allocations"][0]["company_id"] == str(company.id)
    assert tx_data["allocations"][0]["amount"] == "250.00"
    assert tx_data["allocations"][0]["sync_status"] == "PENDING"

    # 3. Test duplicate creation rejected with 409
    dup_resp = client.post("/api/transactions", json=tx_payload, headers=auth_headers)
    assert dup_resp.status_code == 409

    # 4. List transactions with pagination
    list_resp = client.get("/api/transactions?page=1&page_size=10", headers=auth_headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] == 1
    assert list_data["items"][0]["id"] == tx_id

    # 5. Update transaction metadata
    update_resp = client.put(f"/api/transactions/{tx_id}", json={"description": "Hardware & Office Setup (Reviewed)"}, headers=auth_headers)
    assert update_resp.status_code == 200
    assert update_resp.json()["description"] == "Hardware & Office Setup (Reviewed)"

    # 6. Upload receipt file
    receipt_bytes = b"PDF dummy content for receipt test"
    files = {"file": ("acme_receipt.pdf", io.BytesIO(receipt_bytes), "application/pdf")}
    receipt_upload_resp = client.post(f"/api/transactions/{tx_id}/receipt", files=files, headers=auth_headers)
    assert receipt_upload_resp.status_code == 200
    receipt_file_path = receipt_upload_resp.json()["receipt_file_path"]
    assert receipt_file_path is not None

    # Retrieve receipt file
    get_receipt_resp = client.get(f"/api/receipts/{receipt_file_path}", headers=auth_headers)
    assert get_receipt_resp.status_code == 200
    assert get_receipt_resp.content == receipt_bytes

    # 7. Update split allocations
    allocations_payload = [
        {
            "amount": "100.00",
            "is_personal": True,
            "sync_status": "PENDING",
        },
        {
            "amount": "150.00",
            "is_personal": False,
            "company_id": str(company.id),
            "sync_status": "PENDING",
        },
    ]
    alloc_resp = client.put(f"/api/transactions/{tx_id}/allocations", json=allocations_payload, headers=auth_headers)
    assert alloc_resp.status_code == 200
    alloc_data = alloc_resp.json()
    assert len(alloc_data) == 2
    assert alloc_data[0]["is_personal"] is True
    assert alloc_data[1]["company_id"] == str(company.id)

    # 8. Simulate sync to Wave: set business allocation sync_status to SYNCED
    tx = client.get(f"/api/transactions/{tx_id}", headers=auth_headers).json()
    assert len(tx["allocations"]) == 2

    # Manually mark business allocation SYNCED in DB
    import uuid

    from models.transaction import Transaction

    db_tx = db_session.get(Transaction, uuid.UUID(tx_id))
    business_alloc = [a for a in db_tx.allocations if not a.is_personal][0]
    business_alloc.sync_status = SyncStatus.SYNCED
    db_session.commit()

    # 9. Verify immutability validation:
    # Cannot modify allocations when SYNCED
    imm_resp1 = client.put(f"/api/transactions/{tx_id}/allocations", json=[], headers=auth_headers)
    assert imm_resp1.status_code == 400
    assert "SYNCED" in imm_resp1.json()["detail"]

    # Cannot modify transaction metadata when SYNCED
    imm_resp2 = client.put(f"/api/transactions/{tx_id}", json={"description": "Try modifying"}, headers=auth_headers)
    assert imm_resp2.status_code == 400
    assert "SYNCED" in imm_resp2.json()["detail"]

    # Cannot delete transaction when SYNCED
    imm_resp3 = client.delete(f"/api/transactions/{tx_id}", headers=auth_headers)
    assert imm_resp3.status_code == 400
    assert "SYNCED" in imm_resp3.json()["detail"]
