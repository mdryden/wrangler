from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from main import app

MOCK_ADMIN = "mock_admin_user"
MOCK_PASSWORD = "mock_admin_pass_123"
MOCK_SECRET_KEY = "mock-secret-key-that-is-at-least-32-characters-long!"
MOCK_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def set_mock_env(monkeypatch):
    """Ensure tests run against controlled mock configuration rather than host environment."""
    monkeypatch.setattr(settings, "ADMIN_USERNAME", MOCK_ADMIN)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", MOCK_PASSWORD)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", MOCK_SECRET_KEY)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", MOCK_ALGORITHM)
    monkeypatch.setattr(settings, "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 60)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_login_success(client):
    response = client.post(
        "/api/login",
        json={"username": MOCK_ADMIN, "password": MOCK_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)


def test_login_invalid_username(client):
    response = client.post(
        "/api/login",
        json={"username": "wrong_user", "password": MOCK_PASSWORD},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_login_invalid_password(client):
    response = client.post(
        "/api/login",
        json={"username": MOCK_ADMIN, "password": "wrong_password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_login_empty_payload(client):
    response = client.post("/api/login", json={})
    assert response.status_code == 422


def test_login_missing_password(client):
    response = client.post("/api/login", json={"username": MOCK_ADMIN})
    assert response.status_code == 422


def test_protected_route_with_valid_token(client):
    # First login to obtain token
    login_res = client.post(
        "/api/login",
        json={"username": MOCK_ADMIN, "password": MOCK_PASSWORD},
    )
    token = login_res.json()["access_token"]

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"username": MOCK_ADMIN}


def test_protected_route_missing_authorization_header(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_protected_route_invalid_token(client):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_protected_route_expired_token(client):
    expired_token = create_access_token(
        data={"sub": MOCK_ADMIN},
        secret_key=MOCK_SECRET_KEY,
        algorithm=MOCK_ALGORITHM,
        expires_delta=timedelta(seconds=-10),
    )
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


def test_protected_route_wrong_secret(client):
    foreign_token = create_access_token(
        data={"sub": MOCK_ADMIN},
        secret_key="some-different-secret-key-32-chars-long!",
        algorithm=MOCK_ALGORITHM,
    )
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {foreign_token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


def test_protected_route_non_admin_subject(client):
    non_admin_token = create_access_token(
        data={"sub": "random_intruder"},
        secret_key=MOCK_SECRET_KEY,
        algorithm=MOCK_ALGORITHM,
    )
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {non_admin_token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


def test_protected_route_missing_sub_claim(client):
    no_sub_token = create_access_token(
        data={"other_claim": "hello"},
        secret_key=MOCK_SECRET_KEY,
        algorithm=MOCK_ALGORITHM,
    )
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {no_sub_token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


def test_protected_route_invalid_scheme(client):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_unadorned_endpoint_requires_auth_by_default(client):
    """Verify that an endpoint without user parameter is blocked by default without a token."""
    response = client.get("/api/protected")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_unadorned_endpoint_blocks_invalid_token(client):
    """Verify that an endpoint without user parameter blocks invalid tokens."""
    response = client.get(
        "/api/protected",
        headers={"Authorization": "Bearer invalid-garbage-token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


def test_unadorned_endpoint_succeeds_with_valid_token(client):
    """Verify that an endpoint without user parameter allows access with a valid token."""
    login_res = client.post(
        "/api/login",
        json={"username": MOCK_ADMIN, "password": MOCK_PASSWORD},
    )
    token = login_res.json()["access_token"]

    response = client.get(
        "/api/protected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "authenticated"}


def test_opt_in_anonymous_routes_accessible_without_token(client):
    """Verify that only explicitly opted-in routes (health, login) are accessible anonymously."""
    # Health check is opted in
    health_res = client.get("/api/health")
    assert health_res.status_code == 200

    # Login is opted in
    login_res = client.post(
        "/api/login",
        json={"username": MOCK_ADMIN, "password": MOCK_PASSWORD},
    )
    assert login_res.status_code == 200
