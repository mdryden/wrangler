import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.company import Company

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
    assert client.post("/api/companies", json={"name": "X", "wave_equity_account_id": "1"}).status_code == 401
    assert client.get(f"/api/companies/{random_id}").status_code == 401
    assert client.put(f"/api/companies/{random_id}", json={"name": "Y"}).status_code == 401
    assert client.delete(f"/api/companies/{random_id}").status_code == 401


def test_create_company_success(client, auth_headers, db_session):
    payload = {
        "name": "Acme Corporation",
        "wave_equity_account_id": "equity_account_123",
        "wave_business_id": "biz_wave_abc",
    }
    response = client.post("/api/companies", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Acme Corporation"
    assert data["wave_equity_account_id"] == "equity_account_123"
    assert data["wave_business_id"] == "biz_wave_abc"
    assert "id" in data
    assert data["is_connected"] is False

    # Check persistence in db
    company_id = uuid.UUID(data["id"])
    db_company = db_session.get(Company, company_id)
    assert db_company is not None
    assert db_company.name == "Acme Corporation"
    assert db_company.wave_equity_account_id == "equity_account_123"


def test_create_company_validation_error(client, auth_headers):
    # Missing name
    res1 = client.post(
        "/api/companies",
        json={"wave_equity_account_id": "equity_account_123"},
        headers=auth_headers,
    )
    assert res1.status_code == 422

    # Missing wave_equity_account_id
    res2 = client.post(
        "/api/companies",
        json={"name": "Acme Corp"},
        headers=auth_headers,
    )
    assert res2.status_code == 422

    # Empty name
    res3 = client.post(
        "/api/companies",
        json={"name": "", "wave_equity_account_id": "123"},
        headers=auth_headers,
    )
    assert res3.status_code == 422


def test_list_companies(client, auth_headers):
    # Initially empty
    res = client.get("/api/companies", headers=auth_headers)
    assert res.status_code == 200
    assert res.json() == []

    # Create two companies
    client.post(
        "/api/companies",
        json={"name": "Beta Enterprises", "wave_equity_account_id": "eq_beta"},
        headers=auth_headers,
    )
    client.post(
        "/api/companies",
        json={"name": "Alpha Solutions", "wave_equity_account_id": "eq_alpha"},
        headers=auth_headers,
    )

    res = client.get("/api/companies", headers=auth_headers)
    assert res.status_code == 200
    names = [c["name"] for c in res.json()]
    assert names == ["Alpha Solutions", "Beta Enterprises"]


def test_get_company_by_id(client, auth_headers):
    create_res = client.post(
        "/api/companies",
        json={"name": "Sole Proprietor", "wave_equity_account_id": "eq_sole"},
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
        json={"name": "Original Name", "wave_equity_account_id": "eq_orig"},
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
    assert data["wave_equity_account_id"] == "eq_orig"

    # Verify in DB
    db_company = db_session.get(Company, uuid.UUID(company_id))
    assert db_company.name == "Updated Name"

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
        json={"name": "To Delete", "wave_equity_account_id": "eq_del"},
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
