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


def test_companies_unauthenticated_requests_blocked(client):
    random_id = uuid.uuid4()
    assert client.get("/api/companies").status_code == 401
    assert client.post("/api/companies", json={"name": "X"}).status_code == 401
    assert client.get(f"/api/companies/{random_id}").status_code == 401
    assert client.put(f"/api/companies/{random_id}", json={"name": "Y"}).status_code == 401
    assert client.delete(f"/api/companies/{random_id}").status_code == 401


def test_create_company_success(client, auth_headers, db_session):
    payload = {
        "name": "Acme Corporation",
    }
    response = client.post("/api/companies", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Acme Corporation"
    assert "id" in data
    assert "wave_equity_account_id" not in data
    assert "wave_business_id" not in data
    assert "is_connected" not in data

    # Check persistence in db
    company_id = uuid.UUID(data["id"])
    db_company = db_session.get(Company, company_id)
    assert db_company is not None
    assert db_company.name == "Acme Corporation"


def test_create_company_duplicate_name_conflict(client, auth_headers):
    client.post("/api/companies", json={"name": "Duplicate Corp"}, headers=auth_headers)
    res = client.post("/api/companies", json={"name": "Duplicate Corp"}, headers=auth_headers)
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]


def test_create_company_validation_error(client, auth_headers):
    # Missing name
    res1 = client.post(
        "/api/companies",
        json={},
        headers=auth_headers,
    )
    assert res1.status_code == 422

    # Empty name
    res2 = client.post(
        "/api/companies",
        json={"name": ""},
        headers=auth_headers,
    )
    assert res2.status_code == 422


def test_list_companies(client, auth_headers):
    # Initially empty
    res = client.get("/api/companies", headers=auth_headers)
    assert res.status_code == 200
    assert res.json() == []

    # Create two companies
    client.post(
        "/api/companies",
        json={"name": "Beta Enterprises"},
        headers=auth_headers,
    )
    client.post(
        "/api/companies",
        json={"name": "Alpha Solutions"},
        headers=auth_headers,
    )

    res = client.get("/api/companies", headers=auth_headers)
    assert res.status_code == 200
    names = [c["name"] for c in res.json()]
    assert names == ["Alpha Solutions", "Beta Enterprises"]


def test_get_company_by_id(client, auth_headers):
    create_res = client.post(
        "/api/companies",
        json={"name": "Sole Proprietor"},
        headers=auth_headers,
    )
    company_id = create_res.json()["id"]

    # Success
    res = client.get(f"/api/companies/{company_id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["id"] == company_id
    assert res.json()["name"] == "Sole Proprietor"

    # Not found
    non_existent = uuid.uuid4()
    res_nf = client.get(f"/api/companies/{non_existent}", headers=auth_headers)
    assert res_nf.status_code == 404


def test_update_company(client, auth_headers, db_session):
    create_res = client.post(
        "/api/companies",
        json={"name": "Original Name"},
        headers=auth_headers,
    )
    company_id = create_res.json()["id"]

    # Partial update
    update_res = client.put(
        f"/api/companies/{company_id}",
        json={"name": "Updated Name"},
        headers=auth_headers,
    )
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["name"] == "Updated Name"

    # Verify in DB
    db_company = db_session.get(Company, uuid.UUID(company_id))
    assert db_company.name == "Updated Name"

    # Update to duplicate name
    client.post("/api/companies", json={"name": "Other Company"}, headers=auth_headers)
    dup_res = client.put(
        f"/api/companies/{company_id}",
        json={"name": "Other Company"},
        headers=auth_headers,
    )
    assert dup_res.status_code == 409

    # Update not found
    non_existent = uuid.uuid4()
    nf_res = client.put(
        f"/api/companies/{non_existent}",
        json={"name": "Does Not Exist"},
        headers=auth_headers,
    )
    assert nf_res.status_code == 404


def test_delete_company(client, auth_headers, db_session):
    create_res = client.post(
        "/api/companies",
        json={"name": "To Delete"},
        headers=auth_headers,
    )
    company_id = create_res.json()["id"]

    # Delete existing
    del_res = client.delete(f"/api/companies/{company_id}", headers=auth_headers)
    assert del_res.status_code == 204

    # Verify deleted
    get_res = client.get(f"/api/companies/{company_id}", headers=auth_headers)
    assert get_res.status_code == 404
    assert db_session.get(Company, uuid.UUID(company_id)) is None

    # Delete non-existent
    del_nf = client.delete(f"/api/companies/{company_id}", headers=auth_headers)
    assert del_nf.status_code == 404


def test_delete_company_blocked_when_linked_to_allocations(client, auth_headers, db_session):
    # Create company
    create_res = client.post(
        "/api/companies",
        json={"name": "Linked Company"},
        headers=auth_headers,
    )
    company_id = uuid.UUID(create_res.json()["id"])

    # Create transaction and allocation linked to company
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Office Expense",
        total_amount=Decimal("150.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("150.00"),
        is_personal=False,
        company_id=company_id,
    )
    db_session.add(alloc)
    db_session.commit()

    # Attempt to delete company
    del_res = client.delete(f"/api/companies/{company_id}", headers=auth_headers)
    assert del_res.status_code == 400
    assert "linked to existing allocations" in del_res.json()["detail"]

    # Verify company still exists
    db_company = db_session.get(Company, company_id)
    assert db_company is not None
