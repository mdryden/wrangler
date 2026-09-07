import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.company import Company
from services.wave import generate_oauth_state, verify_oauth_state

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
    monkeypatch.setattr(settings, "WAVE_CLIENT_ID", "test_client_id_123")
    monkeypatch.setattr(settings, "WAVE_CLIENT_SECRET", "test_client_secret_xyz")
    monkeypatch.setattr(settings, "WAVE_REDIRECT_URI", "http://localhost:8000/api/wave/oauth/callback")


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


def test_authorize_unauthenticated_blocked(client):
    company_id = uuid.uuid4()
    response = client.get(f"/api/wave/oauth/authorize?company_id={company_id}")
    assert response.status_code == 401


def test_authorize_company_not_found(client, auth_headers):
    random_id = uuid.uuid4()
    response = client.get(
        f"/api/wave/oauth/authorize?company_id={random_id}",
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_authorize_success_returns_json(client, auth_headers, db_session):
    company = Company(name="Wave Co", wave_equity_account_id="eq_wave_1")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    response = client.get(
        f"/api/wave/oauth/authorize?company_id={company.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert "redirect_url" in data
    assert data["authorization_url"] == data["redirect_url"]

    url = data["authorization_url"]
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert params["client_id"] == ["test_client_id_123"]
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == ["http://localhost:8000/api/wave/oauth/callback"]
    assert params["scope"] == ["business:read account:read transaction:write"]

    state = params["state"][0]
    extracted_company_id = verify_oauth_state(state)
    assert extracted_company_id == company.id


def test_authorize_redirect_flag(client, auth_headers, db_session):
    company = Company(name="Redirect Co", wave_equity_account_id="eq_red_1")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    response = client.get(
        f"/api/wave/oauth/authorize?company_id={company.id}&redirect=true",
        headers=auth_headers,
        follow_redirects=False,
    )
    assert response.status_code == 307
    location = response.headers["Location"]
    assert location.startswith(settings.WAVE_AUTHORIZE_URL.rstrip("/"))


def test_callback_accessible_anonymously_missing_params(client):
    # No Authorization header, missing params returns 400 (not 401!)
    res = client.get("/api/wave/oauth/callback")
    assert res.status_code == 400
    assert "missing" in res.json()["detail"].lower()


def test_callback_with_oauth_error(client):
    res = client.get("/api/wave/oauth/callback?error=access_denied")
    assert res.status_code == 400
    assert "access_denied" in res.json()["detail"]


def test_callback_missing_state(client):
    res = client.get("/api/wave/oauth/callback?code=some_auth_code")
    assert res.status_code == 400
    assert "missing oauth state" in res.json()["detail"].lower()


def test_callback_invalid_or_expired_state(client):
    # Completely invalid state
    res = client.get("/api/wave/oauth/callback?code=some_code&state=invalid_token")
    assert res.status_code == 400

    # Expired state
    company_id = uuid.uuid4()
    expired_state = generate_oauth_state(company_id, expires_in_minutes=-10)
    res_exp = client.get(f"/api/wave/oauth/callback?code=some_code&state={expired_state}")
    assert res_exp.status_code == 400


def test_callback_company_not_found(client, monkeypatch):
    non_existent_id = uuid.uuid4()
    state = generate_oauth_state(non_existent_id)
    res = client.get(f"/api/wave/oauth/callback?code=some_code&state={state}")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_callback_success_updates_company(client, db_session, monkeypatch):
    company = Company(name="Callback Co", wave_equity_account_id="eq_cb_1")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    state = generate_oauth_state(company.id)

    # Mock exchange_oauth_code
    def mock_exchange(code, http_client=None):
        assert code == "valid_mock_code"
        return {
            "access_token": "wave_new_access_token_123",
            "refresh_token": "wave_new_refresh_token_456",
            "token_type": "Bearer",
            "expires_in": 7200,
        }

    monkeypatch.setattr("routers.wave_oauth.exchange_oauth_code", mock_exchange)

    res = client.get(f"/api/wave/oauth/callback?code=valid_mock_code&state={state}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(company.id)
    assert data["wave_access_token"] == "wave_new_access_token_123"
    assert data["wave_refresh_token"] == "wave_new_refresh_token_456"
    assert data["is_connected"] is True

    # Verify persisted in database
    db_session.refresh(company)
    assert company.wave_access_token == "wave_new_access_token_123"
    assert company.wave_refresh_token == "wave_new_refresh_token_456"
    expires_at = company.wave_token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    assert expires_at > datetime.now(UTC)


def test_callback_exchange_failure_returns_bad_gateway(client, db_session, monkeypatch):
    company = Company(name="Failure Co", wave_equity_account_id="eq_fail_1")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    state = generate_oauth_state(company.id)

    from services.wave import WaveAuthError

    def mock_exchange(code, http_client=None):
        raise WaveAuthError("Wave server error 500")

    monkeypatch.setattr("routers.wave_oauth.exchange_oauth_code", mock_exchange)

    res = client.get(f"/api/wave/oauth/callback?code=bad_code&state={state}")
    assert res.status_code == 502
    assert "Wave server error 500" in res.json()["detail"]
