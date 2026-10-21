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
from models.wave_category import WaveCategory

MOCK_ADMIN = "admin"
MOCK_PASSWORD = "admin"
MOCK_SECRET_KEY = "mock-secret-key-that-is-at-least-32-characters-long!"
MOCK_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def set_mock_env(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", MOCK_ADMIN)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", MOCK_PASSWORD)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", MOCK_SECRET_KEY)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", MOCK_ALGORITHM)


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


def test_lock_allocation_unauthenticated_blocked(client):
    fake_id = uuid.uuid4()
    resp = client.put(f"/api/allocations/{fake_id}/lock", json={"is_locked": True})
    assert resp.status_code == 401


def test_lock_allocation_not_found(client, auth_headers):
    fake_id = uuid.uuid4()
    resp = client.put(f"/api/allocations/{fake_id}/lock", json={"is_locked": True}, headers=auth_headers)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_lock_and_unlock_allocation_success(client, auth_headers, db_session):
    company = Company(name="Test Corp")
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 1),
        description="Lock test transaction",
        total_amount=Decimal("150.00"),
    )
    db_session.add_all([company, tx])
    db_session.flush()

    alloc = Allocation(
        transaction_id=tx.id,
        company_id=company.id,
        amount=Decimal("150.00"),
        is_personal=False,
        is_locked=False,
    )
    db_session.add(alloc)
    db_session.commit()

    # 1. Lock the allocation via PUT /api/allocations/{id}/lock
    lock_resp = client.put(f"/api/allocations/{alloc.id}/lock", json={"is_locked": True}, headers=auth_headers)
    assert lock_resp.status_code == 200
    assert lock_resp.json()["is_locked"] is True

    # Seed wave_transaction_id on locked allocation
    alloc.wave_transaction_id = "wave_sample_id"
    db_session.add(alloc)
    db_session.commit()

    # Verify parent transaction editing is blocked when locked
    edit_payload = [{"amount": "150.00", "is_personal": True}]
    block_resp = client.put(f"/api/transactions/{tx.id}/allocations", json=edit_payload, headers=auth_headers)
    assert block_resp.status_code == 400

    # 2. Unlock allocation via PUT /api/allocations/{id}/lock
    unlock_resp = client.put(f"/api/allocations/{alloc.id}/lock", json={"is_locked": False}, headers=auth_headers)
    assert unlock_resp.status_code == 200
    data = unlock_resp.json()
    assert data["id"] == str(alloc.id)
    assert data["is_locked"] is False
    assert data["wave_transaction_id"] is None

    # Database verification
    db_session.expire_all()
    refreshed = db_session.get(Allocation, alloc.id)
    assert refreshed is not None
    assert refreshed.is_locked is False
    assert refreshed.wave_transaction_id is None

    # Transaction is now unlocked and can be modified
    allow_resp = client.put(f"/api/transactions/{tx.id}/allocations", json=edit_payload, headers=auth_headers)
    assert allow_resp.status_code == 200
    assert len(allow_resp.json()) == 1
    assert allow_resp.json()[0]["is_personal"] is True


def test_bulk_category_success(client, auth_headers, db_session):
    company = Company(name="Corp A")
    db_session.add(company)
    db_session.flush()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_supplies",
        name="Supplies",
        account_type="EXPENSE",
    )
    tx1 = Transaction(
        source="manual",
        date=date(2026, 9, 1),
        description="Expense 1",
        total_amount=Decimal("50.00"),
    )
    tx2 = Transaction(
        source="manual",
        date=date(2026, 9, 2),
        description="Expense 2",
        total_amount=Decimal("75.00"),
    )
    db_session.add_all([category, tx1, tx2])
    db_session.flush()

    alloc1 = Allocation(
        transaction_id=tx1.id,
        company_id=company.id,
        amount=Decimal("50.00"),
        is_personal=False,
        is_locked=False,
    )
    alloc2 = Allocation(
        transaction_id=tx2.id,
        company_id=company.id,
        amount=Decimal("75.00"),
        is_personal=False,
        is_locked=False,
    )
    db_session.add_all([alloc1, alloc2])
    db_session.commit()

    payload = {
        "allocation_ids": [str(alloc1.id), str(alloc2.id)],
        "wave_category_id": str(category.id),
    }
    resp = client.post("/api/allocations/bulk-category", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated_count"] == 2
    assert set(data["allocation_ids"]) == {str(alloc1.id), str(alloc2.id)}

    db_session.expire_all()
    refreshed1 = db_session.get(Allocation, alloc1.id)
    refreshed2 = db_session.get(Allocation, alloc2.id)
    assert refreshed1.wave_category_id == category.id
    assert refreshed2.wave_category_id == category.id


def test_bulk_category_locked_allocation_rejected(client, auth_headers, db_session):
    company = Company(name="Corp A")
    db_session.add(company)
    db_session.flush()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_supplies",
        name="Supplies",
        account_type="EXPENSE",
    )
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 1),
        description="Expense",
        total_amount=Decimal("100.00"),
    )
    db_session.add_all([category, tx])
    db_session.flush()

    alloc_unlocked = Allocation(
        transaction_id=tx.id,
        company_id=company.id,
        amount=Decimal("50.00"),
        is_personal=False,
        is_locked=False,
    )
    alloc_locked = Allocation(
        transaction_id=tx.id,
        company_id=company.id,
        amount=Decimal("50.00"),
        is_personal=False,
        is_locked=True,
    )
    db_session.add_all([alloc_unlocked, alloc_locked])
    db_session.commit()

    payload = {
        "allocation_ids": [str(alloc_unlocked.id), str(alloc_locked.id)],
        "wave_category_id": str(category.id),
    }
    resp = client.post("/api/allocations/bulk-category", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert "locked and cannot be modified" in resp.json()["detail"]

    # Ensure database state is completely unmutated
    db_session.expire_all()
    refreshed = db_session.get(Allocation, alloc_unlocked.id)
    assert refreshed.wave_category_id is None


def test_bulk_category_mismatched_company_rejected(client, auth_headers, db_session):
    company_a = Company(name="Corp A")
    company_b = Company(name="Corp B")
    db_session.add_all([company_a, company_b])
    db_session.flush()

    category_a = WaveCategory(
        company_id=company_a.id,
        wave_account_id="acc_supplies",
        name="Supplies",
        account_type="EXPENSE",
    )
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 1),
        description="Expense",
        total_amount=Decimal("100.00"),
    )
    db_session.add_all([category_a, tx])
    db_session.flush()

    alloc_b = Allocation(
        transaction_id=tx.id,
        company_id=company_b.id,
        amount=Decimal("100.00"),
        is_personal=False,
        is_locked=False,
    )
    db_session.add(alloc_b)
    db_session.commit()

    payload = {
        "allocation_ids": [str(alloc_b.id)],
        "wave_category_id": str(category_a.id),
    }
    resp = client.post("/api/allocations/bulk-category", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert "does not belong to the category's company" in resp.json()["detail"]


def test_bulk_category_personal_allocation_rejected(client, auth_headers, db_session):
    company = Company(name="Corp A")
    db_session.add(company)
    db_session.flush()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_supplies",
        name="Supplies",
        account_type="EXPENSE",
    )
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 1),
        description="Personal Expense",
        total_amount=Decimal("100.00"),
    )
    db_session.add_all([category, tx])
    db_session.flush()

    alloc_personal = Allocation(
        transaction_id=tx.id,
        company_id=None,
        amount=Decimal("100.00"),
        is_personal=True,
        is_locked=False,
    )
    db_session.add(alloc_personal)
    db_session.commit()

    payload = {
        "allocation_ids": [str(alloc_personal.id)],
        "wave_category_id": str(category.id),
    }
    resp = client.post("/api/allocations/bulk-category", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert "does not belong to the category's company" in resp.json()["detail"]


def test_bulk_category_invalid_category_id(client, auth_headers, db_session):
    company = Company(name="Corp A")
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 1),
        description="Expense",
        total_amount=Decimal("50.00"),
    )
    db_session.add_all([company, tx])
    db_session.flush()

    alloc = Allocation(
        transaction_id=tx.id,
        company_id=company.id,
        amount=Decimal("50.00"),
        is_personal=False,
        is_locked=False,
    )
    db_session.add(alloc)
    db_session.commit()

    fake_cat_id = uuid.uuid4()
    payload = {
        "allocation_ids": [str(alloc.id)],
        "wave_category_id": str(fake_cat_id),
    }
    resp = client.post("/api/allocations/bulk-category", json=payload, headers=auth_headers)
    assert resp.status_code == 404
    assert f"WaveCategory with ID '{fake_cat_id}' not found" in resp.json()["detail"]


def test_bulk_category_missing_allocations(client, auth_headers, db_session):
    company = Company(name="Corp A")
    db_session.add(company)
    db_session.flush()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_supplies",
        name="Supplies",
        account_type="EXPENSE",
    )
    db_session.add(category)
    db_session.commit()

    missing_id_1 = uuid.uuid4()
    missing_id_2 = uuid.uuid4()
    payload = {
        "allocation_ids": [str(missing_id_1), str(missing_id_2)],
        "wave_category_id": str(category.id),
    }
    resp = client.post("/api/allocations/bulk-category", json=payload, headers=auth_headers)
    assert resp.status_code == 404
    assert "Allocations not found:" in resp.json()["detail"]
    assert str(missing_id_1) in resp.json()["detail"]
    assert str(missing_id_2) in resp.json()["detail"]


def test_bulk_category_empty_list_rejected(client, auth_headers, db_session):
    company = Company(name="Corp A")
    db_session.add(company)
    db_session.flush()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_supplies",
        name="Supplies",
        account_type="EXPENSE",
    )
    db_session.add(category)
    db_session.commit()

    payload = {
        "allocation_ids": [],
        "wave_category_id": str(category.id),
    }
    resp = client.post("/api/allocations/bulk-category", json=payload, headers=auth_headers)
    assert resp.status_code == 422
