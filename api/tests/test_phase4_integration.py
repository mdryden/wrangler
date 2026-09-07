import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from core.config import settings
from database import get_db
from main import app
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
    monkeypatch.setattr(settings, "WAVE_CLIENT_ID", "phase4_client_id")
    monkeypatch.setattr(settings, "WAVE_CLIENT_SECRET", "phase4_client_secret")


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


def test_phase4_end_to_end_category_sync(client, db_session, monkeypatch):
    """Full Phase 4 verification flow:
    1. Authenticate as admin via POST /api/login to get JWT token
    2. Create a company record via POST /api/companies
    3. Update company with wave credentials (wave_business_id, wave_access_token)
    4. Call POST /api/companies/{id}/sync-categories (Initial sync)
    5. Verify categories are created in SQLite database
    6. Call GET /api/companies/{id}/categories and verify response
    7. Simulate modified category names + new category in Wave
    8. Call POST /api/companies/{id}/sync-categories again (Upsert verification)
    9. Verify updated and new records in SQLite database
    """
    # 1. Login
    login_res = client.post("/api/login", json={"username": MOCK_ADMIN, "password": MOCK_PASSWORD})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Company
    company_res = client.post(
        "/api/companies",
        json={
            "name": "Phase 4 Sync Farm",
            "wave_equity_account_id": "equity_sync_001",
            "wave_business_id": "wave_biz_p4",
        },
        headers=auth_headers,
    )
    assert company_res.status_code == 201
    company_id = uuid.UUID(company_res.json()["id"])

    # 3. Update company with access token
    update_res = client.put(
        f"/api/companies/{company_id}",
        json={
            "wave_access_token": "wave_p4_access_token",
            "wave_token_expires_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        },
        headers=auth_headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["is_connected"] is True

    # 4. Mock Wave GraphQL endpoint for initial sync
    accounts_state = [
        {
            "id": "wave_acc_office",
            "name": "Office Supplies & Tech",
            "type": {"name": "Expense", "value": "EXPENSE"},
            "isArchived": False,
        },
        {
            "id": "wave_acc_travel",
            "name": "Travel & Lodging",
            "type": {"name": "Expense", "value": "EXPENSE"},
            "isArchived": False,
        },
        {
            "id": "wave_acc_income",
            "name": "Consulting Revenue",
            "type": {"name": "Income", "value": "INCOME"},
            "isArchived": False,
        },
    ]

    def mock_graphql_handler(request: httpx.Request):
        assert request.headers.get("authorization") == "Bearer wave_p4_access_token"
        return httpx.Response(
            200,
            json={
                "data": {
                    "business": {
                        "id": "wave_biz_p4",
                        "accounts": {
                            "pageInfo": {"currentPage": 1, "totalPages": 1, "totalCount": len(accounts_state)},
                            "edges": [{"node": acc} for acc in accounts_state],
                        },
                    }
                }
            },
        )

    # Monkeypatch the httpx.Client used by WaveClient
    real_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(mock_graphql_handler)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    # Initial Sync
    sync_res = client.post(f"/api/companies/{company_id}/sync-categories", headers=auth_headers)
    assert sync_res.status_code == 200
    synced_categories = sync_res.json()
    assert len(synced_categories) == 3

    # Check names ordered alphabetically
    names = [c["name"] for c in synced_categories]
    assert names == ["Consulting Revenue", "Office Supplies & Tech", "Travel & Lodging"]

    # 5. Check database directly
    db_categories = list(db_session.scalars(select(WaveCategory).where(WaveCategory.company_id == company_id).order_by(WaveCategory.name)).all())
    assert len(db_categories) == 3
    assert db_categories[0].wave_account_id == "wave_acc_income"
    assert db_categories[0].name == "Consulting Revenue"

    # 6. Call GET /api/companies/{id}/categories
    list_res = client.get(f"/api/companies/{company_id}/categories", headers=auth_headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 3

    # 7. Modify accounts in Wave: rename Office Supplies, add Advertising
    accounts_state = [
        {
            "id": "wave_acc_office",
            "name": "Office Supplies (Renamed)",
            "type": {"name": "Expense", "value": "EXPENSE"},
            "isArchived": False,
        },
        {
            "id": "wave_acc_travel",
            "name": "Travel & Lodging",
            "type": {"name": "Expense", "value": "EXPENSE"},
            "isArchived": False,
        },
        {
            "id": "wave_acc_income",
            "name": "Consulting Revenue",
            "type": {"name": "Income", "value": "INCOME"},
            "isArchived": False,
        },
        {
            "id": "wave_acc_ads",
            "name": "Advertising & Marketing",
            "type": {"name": "Expense", "value": "EXPENSE"},
            "isArchived": False,
        },
    ]

    # 8. Trigger sync again (Upsert)
    sync2_res = client.post(f"/api/companies/{company_id}/sync-categories", headers=auth_headers)
    assert sync2_res.status_code == 200
    synced2 = sync2_res.json()
    assert len(synced2) == 4

    names2 = [c["name"] for c in synced2]
    assert "Advertising & Marketing" in names2
    assert "Office Supplies (Renamed)" in names2
    assert "Office Supplies & Tech" not in names2

    # 9. Verify in database
    db_session.expire_all()
    db_categories2 = list(db_session.scalars(select(WaveCategory).where(WaveCategory.company_id == company_id).order_by(WaveCategory.name)).all())
    assert len(db_categories2) == 4
    acc_map = {c.wave_account_id: c.name for c in db_categories2}
    assert acc_map["wave_acc_office"] == "Office Supplies (Renamed)"
    assert acc_map["wave_acc_ads"] == "Advertising & Marketing"
