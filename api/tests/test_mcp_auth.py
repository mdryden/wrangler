from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import settings
from core.security import AuthenticationMiddleware, create_access_token


def create_mcp_auth_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(AuthenticationMiddleware)

    @test_app.get("/mcp/test")
    def mcp_endpoint():
        return {"status": "mcp_ok"}

    @test_app.get("/api/protected")
    def api_endpoint():
        return {"status": "api_ok"}

    return test_app


def test_mcp_auth_unauthenticated_when_api_key_unset(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_KEY", "")
    app = create_mcp_auth_test_app()
    client = TestClient(app)

    response = client.get("/mcp/test")
    assert response.status_code == 200
    assert response.json() == {"status": "mcp_ok"}


def test_mcp_auth_success_via_query_param(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_KEY", "secret-mcp-key-123")
    app = create_mcp_auth_test_app()
    client = TestClient(app)

    response = client.get("/mcp/test?api_key=secret-mcp-key-123")
    assert response.status_code == 200
    assert response.json() == {"status": "mcp_ok"}


def test_mcp_auth_success_via_custom_header(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_KEY", "secret-mcp-key-123")
    app = create_mcp_auth_test_app()
    client = TestClient(app)

    response = client.get("/mcp/test", headers={"x-api-key": "secret-mcp-key-123"})
    assert response.status_code == 200
    assert response.json() == {"status": "mcp_ok"}


def test_mcp_auth_success_via_bearer_header(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_KEY", "secret-mcp-key-123")
    app = create_mcp_auth_test_app()
    client = TestClient(app)

    response = client.get("/mcp/test", headers={"Authorization": "Bearer secret-mcp-key-123"})
    assert response.status_code == 200
    assert response.json() == {"status": "mcp_ok"}


def test_mcp_auth_rejection_missing_or_mismatched_key(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_KEY", "secret-mcp-key-123")
    app = create_mcp_auth_test_app()
    client = TestClient(app)

    # Missing key
    response = client.get("/mcp/test")
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing MCP API key"}

    # Mismatched query parameter
    response = client.get("/mcp/test?api_key=wrong-key")
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing MCP API key"}

    # Mismatched header
    response = client.get("/mcp/test", headers={"x-api-key": "wrong-key"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing MCP API key"}

    # Mismatched Bearer token
    response = client.get("/mcp/test", headers={"Authorization": "Bearer wrong-key"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing MCP API key"}


def test_mcp_auth_non_interference_with_jwt_api_endpoints(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_KEY", "secret-mcp-key-123")
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "secret-key-at-least-32-chars-long")
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    app = create_mcp_auth_test_app()
    client = TestClient(app)

    # Calling /api/protected without JWT fails with standard 401 Not authenticated
    response = client.get("/api/protected")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}

    # Passing MCP key to /api/protected still fails because it's not a JWT
    response = client.get("/api/protected?api_key=secret-mcp-key-123")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}

    # Passing valid JWT succeeds
    token = create_access_token(
        data={"sub": "admin"},
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    response = client.get("/api/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"status": "api_ok"}
