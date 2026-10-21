from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.allocation import Allocation
from models.company import Company
from models.transaction import Transaction
from models.wave_category import WaveCategory
from services.wave.client import WaveApiError, WaveClient

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


def test_patch_allocation_category(client, auth_headers, db_session):
    company = Company(name="Patch Cat Corp")
    db_session.add(company)
    db_session.commit()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="c1",
        name="Office Supplies",
        account_type="EXPENSE",
    )
    other_company = Company(name="Other Corp")
    db_session.add_all([category, other_company])
    db_session.commit()

    other_category = WaveCategory(
        company_id=other_company.id,
        wave_account_id="c2",
        name="Other Supplies",
        account_type="EXPENSE",
    )
    db_session.add(other_category)

    tx = Transaction(
        source="MANUAL",
        date=date(2026, 10, 20),
        description="Office Supplies Purchase",
        total_amount=Decimal("50.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("50.00"),
        is_personal=False,
        company_id=company.id,
        is_locked=False,
    )
    db_session.add(alloc)
    db_session.commit()

    # Successfully assigns category to unlocked allocation
    resp = client.patch(
        f"/api/allocations/{alloc.id}/category",
        json={"wave_category_id": str(category.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["wave_category_id"] == str(category.id)

    # Category belonging to different company returns HTTP 400
    resp_other = client.patch(
        f"/api/allocations/{alloc.id}/category",
        json={"wave_category_id": str(other_category.id)},
        headers=auth_headers,
    )
    assert resp_other.status_code == 400
    assert resp_other.json()["detail"] == "Invalid category for this company"

    # Locked allocation returns HTTP 400
    alloc.is_locked = True
    db_session.commit()

    resp_locked = client.patch(
        f"/api/allocations/{alloc.id}/category",
        json={"wave_category_id": str(category.id)},
        headers=auth_headers,
    )
    assert resp_locked.status_code == 400
    assert resp_locked.json()["detail"] == "Cannot change category on a locked allocation"


def test_sync_wave_unlinked_company(client, auth_headers, db_session):
    company = Company(name="Unlinked Corp")
    db_session.add(company)
    db_session.commit()

    resp = client.post(f"/api/companies/{company.id}/sync-wave", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Company is not connected to Wave"


def test_sync_wave_already_synced_safeguard(client, auth_headers, db_session):
    company = Company(
        name="Safeguard Corp",
        wave_api_token="tok_123",
        wave_business_id="biz_123",
        wave_business_name="Biz",
        wave_anchor_account_id="anchor_123",
    )
    db_session.add(company)
    db_session.commit()

    tx = Transaction(
        source="MANUAL",
        date=date(2026, 10, 20),
        description="Duplicate Sync Test",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("100.00"),
        is_personal=False,
        company_id=company.id,
        is_locked=False,
        wave_transaction_id="wave_existing_tx_id",
    )
    db_session.add(alloc)
    db_session.commit()

    resp = client.post(
        f"/api/companies/{company.id}/sync-wave",
        json={"allocation_ids": [str(alloc.id)]},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert f"Allocation {alloc.id} was already synced to Wave" in resp.json()["detail"]


def test_sync_wave_category_fallback_and_validation(client, auth_headers, db_session):
    company = Company(
        name="Fallback Corp",
        wave_api_token="tok_123",
        wave_business_id="biz_123",
        wave_business_name="Biz",
        wave_anchor_account_id="anchor_123",
    )
    db_session.add(company)
    db_session.commit()

    tx = Transaction(
        source="MANUAL",
        date=date(2026, 10, 20),
        description="No Category Tx",
        total_amount=Decimal("50.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("50.00"),
        is_personal=False,
        company_id=company.id,
        is_locked=False,
        wave_category_id=None,
    )
    db_session.add(alloc)
    db_session.commit()

    # When no uncategorized fallback exists -> HTTP 400
    resp_no_fallback = client.post(f"/api/companies/{company.id}/sync-wave", headers=auth_headers)
    assert resp_no_fallback.status_code == 400
    assert "requires a category before syncing" in resp_no_fallback.json()["detail"]

    # Add uncategorized fallback category
    uncat = WaveCategory(
        company_id=company.id,
        wave_account_id="uncat_acct_id",
        name="Uncategorized Expense",
        account_type="EXPENSE",
        account_subtype="UNCATEGORIZED_EXPENSE",
        is_uncategorized=True,
    )
    db_session.add(uncat)
    db_session.commit()

    with patch.object(WaveClient, "create_money_transaction", new_callable=AsyncMock, return_value="wave_created_tx"):
        resp = client.post(f"/api/companies/{company.id}/sync-wave", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_processed"] == 1
        assert data["synced_count"] == 1
        assert data["failed_count"] == 0

        # Allocation should be updated with fallback category and locked
        db_session.refresh(alloc)
        assert alloc.is_locked is True
        assert alloc.wave_transaction_id == "wave_created_tx"
        assert alloc.wave_category_id == uncat.id


def test_sync_wave_receipt_memo_formatting_and_partial_sync_resilience(client, auth_headers, db_session):
    company = Company(
        name="Resilience Corp",
        wave_api_token="tok_123",
        wave_business_id="biz_123",
        wave_business_name="Biz",
        wave_anchor_account_id="anchor_123",
    )
    db_session.add(company)
    db_session.commit()

    cat = WaveCategory(
        company_id=company.id,
        wave_account_id="acct_cat_1",
        name="Supplies",
        account_type="EXPENSE",
    )
    db_session.add(cat)

    # Tx 1: with receipt file
    tx1 = Transaction(
        source="MANUAL",
        date=date(2026, 10, 1),
        description="Tx With Receipt",
        total_amount=Decimal("10.00"),
        receipt_file_path="/var/storage/receipts/receipt123.pdf",
    )
    # Tx 2: causes error
    tx2 = Transaction(
        source="MANUAL",
        date=date(2026, 10, 2),
        description="Failing Tx",
        total_amount=Decimal("20.00"),
    )
    # Tx 3: without receipt file
    tx3 = Transaction(
        source="MANUAL",
        date=date(2026, 10, 3),
        description="Tx Without Receipt",
        total_amount=Decimal("30.00"),
    )
    db_session.add_all([tx1, tx2, tx3])
    db_session.commit()

    alloc1 = Allocation(transaction_id=tx1.id, amount=Decimal("10.00"), is_personal=False, company_id=company.id, wave_category_id=cat.id)
    alloc2 = Allocation(transaction_id=tx2.id, amount=Decimal("20.00"), is_personal=False, company_id=company.id, wave_category_id=cat.id)
    alloc3 = Allocation(transaction_id=tx3.id, amount=Decimal("30.00"), is_personal=False, company_id=company.id, wave_category_id=cat.id)
    db_session.add_all([alloc1, alloc2, alloc3])
    db_session.commit()

    captured_descriptions = []
    captured_calls = []

    async def mock_create(**kwargs):
        captured_calls.append(kwargs)
        desc = kwargs.get("description")
        captured_descriptions.append(desc)
        if "Failing Tx" in desc:
            raise WaveApiError("Upstream Wave network error")
        return f"wave_tx_{len(captured_descriptions)}"

    with patch.object(WaveClient, "create_money_transaction", new_callable=AsyncMock, side_effect=mock_create):
        resp = client.post(f"/api/companies/{company.id}/sync-wave", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_processed"] == 3
        assert data["synced_count"] == 2
        assert data["failed_count"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["allocation_id"] == str(alloc2.id)
        assert "Upstream Wave network error" in data["errors"][0]["error"]

        # Check anchor account ID passed to WaveClient
        assert len(captured_calls) == 3
        for call_kw in captured_calls:
            assert call_kw["anchor_account_id"] == "anchor_123"

        # Check description formatting
        assert "Tx With Receipt [Receipt: receipt123.pdf]" in captured_descriptions
        assert "Tx Without Receipt" in captured_descriptions

        # Check atomic per-transaction DB commit: alloc1 and alloc3 locked; alloc2 unlocked
        db_session.refresh(alloc1)
        db_session.refresh(alloc2)
        db_session.refresh(alloc3)

        assert alloc1.is_locked is True
        assert alloc1.wave_transaction_id == "wave_tx_1"

        assert alloc2.is_locked is False
        assert alloc2.wave_transaction_id is None

        assert alloc3.is_locked is True
        assert alloc3.wave_transaction_id == "wave_tx_3"
