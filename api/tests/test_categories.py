import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.company import Company
from models.wave_category import WaveCategory
from services.wave import (
    CHART_OF_ACCOUNTS_QUERY,
    WaveClient,
    WaveConfigurationError,
    WaveError,
    WaveGraphQLError,
    sync_company_categories,
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
    monkeypatch.setattr(settings, "WAVE_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "WAVE_CLIENT_SECRET", "mock_client_secret")


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


def test_chart_of_accounts_query_contains_required_filters():
    """Verify CHART_OF_ACCOUNTS_QUERY has the required filters for Expense, Asset, Income."""
    assert "EXPENSE" in CHART_OF_ACCOUNTS_QUERY
    assert "ASSET" in CHART_OF_ACCOUNTS_QUERY
    assert "INCOME" in CHART_OF_ACCOUNTS_QUERY
    assert "business(id: $businessId)" in CHART_OF_ACCOUNTS_QUERY
    assert "pageInfo" in CHART_OF_ACCOUNTS_QUERY
    assert "edges" in CHART_OF_ACCOUNTS_QUERY
    assert "isArchived" in CHART_OF_ACCOUNTS_QUERY


def test_wave_client_get_chart_of_accounts_missing_business_id():
    company = Company(
        name="No Biz ID Co",
        wave_equity_account_id="equity_1",
        wave_access_token="tok_123",
        wave_business_id=None,
    )
    client = WaveClient(company)
    with pytest.raises(WaveConfigurationError, match="Wave business ID configured"):
        client.get_chart_of_accounts()


def test_wave_client_get_chart_of_accounts_pagination_and_filtering():
    company = Company(
        name="Test Biz Co",
        wave_equity_account_id="equity_1",
        wave_access_token="tok_valid",
        wave_business_id="biz_100",
        wave_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    call_count = 0

    def mock_handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            body = {
                "data": {
                    "business": {
                        "id": "biz_100",
                        "accounts": {
                            "pageInfo": {"currentPage": 1, "totalPages": 2, "totalCount": 4},
                            "edges": [
                                {
                                    "node": {
                                        "id": "acc_1",
                                        "name": "Advertising & Marketing",
                                        "type": {"name": "Expense", "value": "EXPENSE"},
                                        "isArchived": False,
                                    }
                                },
                                {
                                    "node": {
                                        "id": "acc_2_archived",
                                        "name": "Old Deprecated Account",
                                        "type": {"name": "Expense", "value": "EXPENSE"},
                                        "isArchived": True,
                                    }
                                },
                                {
                                    "node": {
                                        "id": "acc_3_liability",
                                        "name": "Loan Liability",
                                        "type": {"name": "Liability", "value": "LIABILITY"},
                                        "isArchived": False,
                                    }
                                },
                            ],
                        },
                    }
                }
            }
        else:
            body = {
                "data": {
                    "business": {
                        "id": "biz_100",
                        "accounts": {
                            "pageInfo": {"currentPage": 2, "totalPages": 2, "totalCount": 4},
                            "edges": [
                                {
                                    "node": {
                                        "id": "acc_4",
                                        "name": "Software & Subscriptions",
                                        "type": {"name": "Expense", "value": "EXPENSE"},
                                        "isArchived": False,
                                    }
                                }
                            ],
                        },
                    }
                }
            }
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    wave_client = WaveClient(company, http_client=http_client)

    accounts = wave_client.get_chart_of_accounts()
    assert call_count == 2
    assert len(accounts) == 2
    assert accounts[0] == {"wave_account_id": "acc_1", "name": "Advertising & Marketing"}
    assert accounts[1] == {"wave_account_id": "acc_4", "name": "Software & Subscriptions"}


def test_wave_client_get_chart_of_accounts_business_not_found():
    company = Company(
        name="Test Biz Co",
        wave_equity_account_id="equity_1",
        wave_access_token="tok_valid",
        wave_business_id="biz_missing",
        wave_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    def mock_handler(request: httpx.Request):
        return httpx.Response(200, json={"data": {"business": None}})

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.Client(transport=transport)
    wave_client = WaveClient(company, http_client=http_client)

    with pytest.raises(WaveError, match="not found or inaccessible"):
        wave_client.get_chart_of_accounts()


def test_sync_company_categories_upsert_logic(db_session):
    company = Company(
        name="Upsert Co",
        wave_equity_account_id="equity_upsert",
        wave_access_token="tok_upsert",
        wave_business_id="biz_upsert",
        wave_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(company)
    db_session.commit()

    # Pre-populate an existing category that will be updated
    cat_existing = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_wave_01",
        name="Old Category Name",
    )
    # Pre-populate another category for a different company to verify scoping
    other_company = Company(
        name="Other Co",
        wave_equity_account_id="equity_other",
    )
    db_session.add(other_company)
    db_session.commit()

    other_cat = WaveCategory(
        company_id=other_company.id,
        wave_account_id="acc_wave_01",
        name="Other Co Category",
    )
    db_session.add_all([cat_existing, other_cat])
    db_session.commit()

    # Mock Wave client returning updated acc_wave_01 and new acc_wave_02
    class MockWaveClient:
        def __init__(self, company, db=None):
            self.company = company

        def get_chart_of_accounts(self):
            return [
                {"wave_account_id": "acc_wave_01", "name": "Updated Category Name"},
                {"wave_account_id": "acc_wave_02", "name": "Brand New Category"},
            ]

    synced = sync_company_categories(company, db_session, client=MockWaveClient(company))
    assert len(synced) == 2

    # Verify in SQLite database
    categories = list(db_session.scalars(select(WaveCategory).where(WaveCategory.company_id == company.id).order_by(WaveCategory.name)).all())
    assert len(categories) == 2
    assert categories[0].wave_account_id == "acc_wave_02"
    assert categories[0].name == "Brand New Category"
    assert categories[1].wave_account_id == "acc_wave_01"
    assert categories[1].name == "Updated Category Name"

    # Verify the other company category is untouched
    db_session.refresh(other_cat)
    assert other_cat.name == "Other Co Category"


def test_sync_categories_endpoint_unauthenticated(client):
    company_id = uuid.uuid4()
    res = client.post(f"/api/companies/{company_id}/sync-categories")
    assert res.status_code == 401


def test_sync_categories_endpoint_company_not_found(client, auth_headers):
    random_id = uuid.uuid4()
    res = client.post(f"/api/companies/{random_id}/sync-categories", headers=auth_headers)
    assert res.status_code == 404


def test_sync_categories_endpoint_not_connected(client, db_session, auth_headers):
    company = Company(
        name="Disconnected Co",
        wave_equity_account_id="equity_disc",
        wave_business_id="biz_disc",
        wave_access_token=None,
    )
    db_session.add(company)
    db_session.commit()

    res = client.post(f"/api/companies/{company.id}/sync-categories", headers=auth_headers)
    assert res.status_code == 400
    assert "not connected" in res.json()["detail"].lower()


def test_sync_categories_endpoint_missing_business_id(client, db_session, auth_headers):
    company = Company(
        name="Missing Biz ID Co",
        wave_equity_account_id="equity_no_biz",
        wave_access_token="tok_has_token",
        wave_business_id=None,
    )
    db_session.add(company)
    db_session.commit()

    res = client.post(f"/api/companies/{company.id}/sync-categories", headers=auth_headers)
    assert res.status_code == 400
    assert "wave business id" in res.json()["detail"].lower()


def test_sync_categories_endpoint_wave_failure(client, db_session, auth_headers, monkeypatch):
    company = Company(
        name="Failing Wave Co",
        wave_equity_account_id="equity_fail",
        wave_access_token="tok_fail",
        wave_business_id="biz_fail",
    )
    db_session.add(company)
    db_session.commit()

    def mock_query(self, query, variables=None):
        raise WaveGraphQLError([{"message": "Wave upstream error"}])

    monkeypatch.setattr(WaveClient, "query_graphql", mock_query)

    res = client.post(f"/api/companies/{company.id}/sync-categories", headers=auth_headers)
    assert res.status_code == 502
    assert "Wave sync error" in res.json()["detail"]


def test_sync_categories_endpoint_success_and_listing(client, db_session, auth_headers, monkeypatch):
    company = Company(
        name="Success Co",
        wave_equity_account_id="equity_succ",
        wave_access_token="tok_succ",
        wave_business_id="biz_succ",
        wave_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(company)
    db_session.commit()

    def mock_get_chart(self, business_id=None, page_size=100):
        return [
            {"wave_account_id": "acc_10", "name": "Office Supplies"},
            {"wave_account_id": "acc_20", "name": "Meals & Entertainment"},
        ]

    monkeypatch.setattr(WaveClient, "get_chart_of_accounts", mock_get_chart)

    # 1. Trigger sync endpoint
    res = client.post(f"/api/companies/{company.id}/sync-categories", headers=auth_headers)
    assert res.status_code == 200
    categories = res.json()
    assert len(categories) == 2
    # Verify sorted by name
    assert categories[0]["name"] == "Meals & Entertainment"
    assert categories[0]["wave_account_id"] == "acc_20"
    assert categories[0]["company_id"] == str(company.id)
    assert categories[1]["name"] == "Office Supplies"
    assert categories[1]["wave_account_id"] == "acc_10"

    # 2. Verify GET /api/companies/{id}/categories endpoint
    list_res = client.get(f"/api/companies/{company.id}/categories", headers=auth_headers)
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert len(list_data) == 2
    assert list_data[0]["name"] == "Meals & Entertainment"
    assert list_data[1]["name"] == "Office Supplies"

    # 3. Verify in database
    db_cats = list(db_session.scalars(select(WaveCategory).where(WaveCategory.company_id == company.id).order_by(WaveCategory.name)).all())
    assert len(db_cats) == 2
    assert db_cats[0].name == "Meals & Entertainment"
    assert db_cats[1].name == "Office Supplies"
