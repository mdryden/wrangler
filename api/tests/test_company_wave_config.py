from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.company import Company
from models.wave_category import WaveCategory
from services.wave.client import (
    WaveAccount,
    WaveAccountsResult,
    WaveApiError,
    WaveAuthError,
    WaveBusiness,
    WaveClient,
)

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


def test_wave_test_token_endpoints(client, auth_headers):
    # Valid token returns business list
    with patch.object(
        WaveClient,
        "get_user_businesses",
        new_callable=AsyncMock,
        return_value=[WaveBusiness(id="b1", name="Business One", is_personal=False)],
    ):
        resp = client.post("/api/companies/wave/test-token", json={"token": "valid-token"}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "b1"
        assert data[0]["name"] == "Business One"
        assert data[0]["is_personal"] is False

    # Invalid token raises 401
    with patch.object(
        WaveClient,
        "get_user_businesses",
        new_callable=AsyncMock,
        side_effect=WaveAuthError("Invalid access token"),
    ):
        resp = client.post("/api/companies/wave/test-token", json={"token": "invalid-token"}, headers=auth_headers)
        assert resp.status_code == 401
        assert "Invalid access token" in resp.json()["detail"]

    # Wave API unreachable raises 502
    with patch.object(
        WaveClient,
        "get_user_businesses",
        new_callable=AsyncMock,
        side_effect=WaveApiError("Network timeout"),
    ):
        resp = client.post("/api/companies/wave/test-token", json={"token": "timeout-token"}, headers=auth_headers)
        assert resp.status_code == 502
        assert "Network timeout" in resp.json()["detail"]


def test_wave_business_accounts_endpoint(client, auth_headers):
    mock_result = WaveAccountsResult(
        anchor_accounts=[
            WaveAccount(id="a1", name="Owner's Equity", type="EQUITY", subtype="OWNERS_EQUITY"),
        ],
        expense_categories=[
            WaveAccount(id="c1", name="Office Supplies", type="EXPENSE", subtype=None, is_uncategorized=False),
            WaveAccount(id="c2", name="Uncategorized Expense", type="EXPENSE", subtype="UNCATEGORIZED_EXPENSE", is_uncategorized=True),
        ],
    )

    with patch.object(WaveClient, "get_business_accounts", new_callable=AsyncMock, return_value=mock_result):
        resp = client.post(
            "/api/companies/wave/business-accounts",
            json={"token": "valid-token", "business_id": "b1"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["anchor_accounts"]) == 1
        assert data["anchor_accounts"][0]["name"] == "Owner's Equity"
        assert len(data["expense_categories"]) == 2
        assert data["expense_categories"][1]["is_uncategorized"] is True


def test_wave_connect_and_disconnect(client, auth_headers, db_session):
    company = Company(name="Wave Integration Test Corp")
    db_session.add(company)
    db_session.commit()

    mock_result = WaveAccountsResult(
        anchor_accounts=[WaveAccount(id="a1", name="Checking", type="ASSET", subtype="CASH_AND_BANK")],
        expense_categories=[
            WaveAccount(id="c1", name="Software Subscriptions", type="EXPENSE", subtype=None, is_uncategorized=False),
            WaveAccount(id="c2", name="Uncategorized Expense", type="EXPENSE", subtype="UNCATEGORIZED_EXPENSE", is_uncategorized=True),
        ],
    )

    with patch.object(WaveClient, "get_business_accounts", new_callable=AsyncMock, return_value=mock_result):
        payload = {
            "token": "tok_123",
            "business_id": "biz_123",
            "business_name": "My Wave Business",
            "anchor_account_id": "a1",
        }
        resp = client.post(f"/api/companies/{company.id}/wave/connect", json=payload, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["wave_business_id"] == "biz_123"
        assert data["wave_business_name"] == "My Wave Business"
        assert data["wave_anchor_account_id"] == "a1"
        assert "wave_equity_account_id" not in data
        assert data["is_wave_connected"] is True

        # Check backward compatibility with equity_account_id
        legacy_payload = {
            "token": "tok_123",
            "business_id": "biz_123",
            "business_name": "My Wave Business",
            "equity_account_id": "a1",
        }
        legacy_resp = client.post(f"/api/companies/{company.id}/wave/connect", json=legacy_payload, headers=auth_headers)
        assert legacy_resp.status_code == 200
        assert legacy_resp.json()["wave_anchor_account_id"] == "a1"

        # Check cached categories created
        categories_resp = client.get(f"/api/companies/{company.id}/wave/categories", headers=auth_headers)
        assert categories_resp.status_code == 200
        cats = categories_resp.json()
        assert len(cats) == 2
        # Uncategorized should be first
        assert cats[0]["is_uncategorized"] is True
        assert cats[0]["name"] == "Uncategorized Expense"
        assert cats[1]["name"] == "Software Subscriptions"

    # Disconnect Wave
    del_resp = client.delete(f"/api/companies/{company.id}/wave", headers=auth_headers)
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["is_wave_connected"] is False
    assert del_data["wave_business_id"] is None
    assert del_data["wave_anchor_account_id"] is None

    # Categories should be deleted
    cats_after = client.get(f"/api/companies/{company.id}/wave/categories", headers=auth_headers).json()
    assert len(cats_after) == 0


def test_wave_sync_categories(client, auth_headers, db_session):
    company = Company(
        name="Category Sync Corp",
        wave_api_token="tok_sync",
        wave_business_id="biz_sync",
        wave_business_name="Sync Business",
        wave_anchor_account_id="a1",
    )
    db_session.add(company)
    db_session.commit()

    # Pre-populate with an old category that should be removed
    old_cat = WaveCategory(
        company_id=company.id,
        wave_account_id="c_old",
        name="Old Deleted Category",
        account_type="EXPENSE",
    )
    db_session.add(old_cat)
    db_session.commit()

    # Sync with new categories
    mock_result = WaveAccountsResult(
        anchor_accounts=[],
        expense_categories=[
            WaveAccount(id="c_new", name="Advertising & Marketing", type="EXPENSE", subtype=None, is_uncategorized=False),
            WaveAccount(id="c_uncat", name="Uncategorized Expense", type="EXPENSE", subtype="UNCATEGORIZED_EXPENSE", is_uncategorized=True),
        ],
    )

    with patch.object(WaveClient, "get_business_accounts", new_callable=AsyncMock, return_value=mock_result):
        resp = client.post(f"/api/companies/{company.id}/wave/sync-categories", headers=auth_headers)
        assert resp.status_code == 200
        cats = resp.json()
        assert len(cats) == 2
        assert cats[0]["name"] == "Uncategorized Expense"
        assert cats[1]["name"] == "Advertising & Marketing"
        # Old category should be pruned
        assert not any(c["wave_account_id"] == "c_old" for c in cats)

    # Calling on unlinked company returns 400
    unlinked_company = Company(name="Unlinked Corp")
    db_session.add(unlinked_company)
    db_session.commit()

    bad_resp = client.post(f"/api/companies/{unlinked_company.id}/wave/sync-categories", headers=auth_headers)
    assert bad_resp.status_code == 400
    assert "not connected to Wave" in bad_resp.json()["detail"]
