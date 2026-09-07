import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from core.config import settings
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
    monkeypatch.setattr(settings, "WAVE_CLIENT_ID", "phase3_client_id")
    monkeypatch.setattr(settings, "WAVE_CLIENT_SECRET", "phase3_client_secret")
    monkeypatch.setattr(settings, "WAVE_REDIRECT_URI", "http://localhost:8000/api/wave/oauth/callback")


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


def test_full_company_and_wave_oauth_flow(client, db_session, monkeypatch):
    """Verifies complete Phase 3 flow:
    1. Authenticate as admin via /api/login
    2. Create company record
    3. Verify and update company record
    4. Generate Wave OAuth authorize redirect URL
    5. Simulate Wave OAuth callback and exchange
    6. Verify tokens persisted in database
    7. Clean up company record
    """
    # 1. Login
    login_res = client.post(
        "/api/login",
        json={"username": MOCK_ADMIN, "password": MOCK_PASSWORD},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Company
    create_payload = {
        "name": "Integration Test Co",
        "wave_equity_account_id": "equity_int_100",
        "wave_business_id": "biz_int_999",
    }
    create_res = client.post("/api/companies", json=create_payload, headers=auth_headers)
    assert create_res.status_code == 201
    company_data = create_res.json()
    company_id = company_data["id"]
    assert company_data["name"] == "Integration Test Co"
    assert company_data["wave_equity_account_id"] == "equity_int_100"
    assert company_data["is_connected"] is False

    # 3. Update Company
    update_res = client.put(
        f"/api/companies/{company_id}",
        json={"name": "Integration Test Co Renamed"},
        headers=auth_headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Integration Test Co Renamed"

    # 4. Generate Wave OAuth Authorize URL
    auth_res = client.get(
        f"/api/wave/oauth/authorize?company_id={company_id}",
        headers=auth_headers,
    )
    assert auth_res.status_code == 200
    auth_url = auth_res.json()["authorization_url"]
    assert auth_url.startswith("https://api.waveapps.com/oauth2/authorize")

    # Extract state parameter from generated URL
    parsed_url = urlparse(auth_url)
    qs = parse_qs(parsed_url.query)
    state = qs["state"][0]
    assert state is not None

    # 5. Simulate Wave OAuth Callback
    def mock_exchange(code, http_client=None):
        assert code == "simulated_auth_code_777"
        return {
            "access_token": "wave_simulated_access_token",
            "refresh_token": "wave_simulated_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    monkeypatch.setattr("routers.wave_oauth.exchange_oauth_code", mock_exchange)

    callback_res = client.get(f"/api/wave/oauth/callback?code=simulated_auth_code_777&state={state}")
    assert callback_res.status_code == 200
    callback_data = callback_res.json()
    assert callback_data["is_connected"] is True
    assert callback_data["wave_access_token"] == "wave_simulated_access_token"
    assert callback_data["wave_refresh_token"] == "wave_simulated_refresh_token"

    # 6. Verify database persistence
    company_obj = db_session.get(Company, uuid.UUID(company_id))
    assert company_obj is not None
    assert company_obj.wave_access_token == "wave_simulated_access_token"
    assert company_obj.wave_refresh_token == "wave_simulated_refresh_token"
    expires_at = company_obj.wave_token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    assert expires_at > datetime.now(UTC)

    # Verify GET /api/companies/{id} reflects connected state
    get_res = client.get(f"/api/companies/{company_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["is_connected"] is True

    # 7. Delete Company
    delete_res = client.delete(f"/api/companies/{company_id}", headers=auth_headers)
    assert delete_res.status_code == 204

    # Verify deleted
    get_del_res = client.get(f"/api/companies/{company_id}", headers=auth_headers)
    assert get_del_res.status_code == 404
