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


def test_revert_allocation_unauthenticated_blocked(client):
    fake_id = uuid.uuid4()
    resp = client.put(f"/api/allocations/{fake_id}/revert")
    assert resp.status_code == 401


def test_revert_allocation_not_found(client, auth_headers):
    fake_id = uuid.uuid4()
    resp = client.put(f"/api/allocations/{fake_id}/revert", headers=auth_headers)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_revert_allocation_success(client, auth_headers, db_session):
    company = Company(name="Test Corp")
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 1),
        description="Revert test transaction",
        total_amount=Decimal("150.00"),
    )
    db_session.add_all([company, tx])
    db_session.flush()

    alloc = Allocation(
        transaction_id=tx.id,
        company_id=company.id,
        amount=Decimal("150.00"),
        is_personal=False,
        sync_status=SyncStatus.SYNCED,
    )
    db_session.add(alloc)
    db_session.commit()

    # Verify parent transaction editing is initially blocked
    edit_payload = [{"amount": "150.00", "is_personal": True}]
    block_resp = client.put(f"/api/transactions/{tx.id}/allocations", json=edit_payload, headers=auth_headers)
    assert block_resp.status_code == 400

    # Revert allocation to PENDING
    revert_resp = client.put(f"/api/allocations/{alloc.id}/revert", headers=auth_headers)
    assert revert_resp.status_code == 200
    data = revert_resp.json()
    assert data["id"] == str(alloc.id)
    assert data["sync_status"] == SyncStatus.PENDING

    # Database verification
    db_session.expire_all()
    refreshed = db_session.get(Allocation, alloc.id)
    assert refreshed is not None
    assert refreshed.sync_status == SyncStatus.PENDING

    # Transaction is now unlocked and can be modified
    allow_resp = client.put(f"/api/transactions/{tx.id}/allocations", json=edit_payload, headers=auth_headers)
    assert allow_resp.status_code == 200
    assert len(allow_resp.json()) == 1
    assert allow_resp.json()[0]["is_personal"] is True


def test_revert_allocation_already_pending(client, auth_headers, db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 1),
        description="Pending test transaction",
        total_amount=Decimal("50.00"),
    )
    db_session.add(tx)
    db_session.flush()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("50.00"),
        is_personal=True,
        sync_status=SyncStatus.PENDING,
    )
    db_session.add(alloc)
    db_session.commit()

    resp = client.put(f"/api/allocations/{alloc.id}/revert", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["sync_status"] == SyncStatus.PENDING
