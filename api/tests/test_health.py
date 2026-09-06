from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from database import get_db
from main import app


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


def test_health_check_healthy(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "healthy"
    assert "meta" in data
    assert "database_path" in data["meta"]
    assert data["meta"]["database_path"] in (":memory:", "wrangler.db")


def test_health_check_unhealthy(client):
    mock_db = MagicMock()
    mock_db.execute.side_effect = OperationalError("SELECT 1", {}, Exception("database is locked"))

    def override_broken_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_broken_db
    try:
        response = client.get("/api/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "unhealthy"
        assert "meta" in data
        assert "error" in data["meta"]
        assert "database is locked" in data["meta"]["error"]
    finally:
        app.dependency_overrides.clear()
