from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.allocation import Allocation
from models.company import Company
from models.transaction import Transaction

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


def test_update_allocations_rejects_duplicate_company(client, auth_headers, db_session):
    company = Company(name="Entity Corp A")
    db_session.add(company)
    db_session.commit()

    tx = Transaction(
        source="MANUAL",
        date=date(2026, 10, 20),
        description="Duplicate Company Test",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("100.00"),
        is_personal=False,
        company_id=company.id,
    )
    db_session.add(alloc)
    db_session.commit()

    payload = [
        {"amount": "40.00", "is_personal": False, "company_id": str(company.id)},
        {"amount": "60.00", "is_personal": False, "company_id": str(company.id)},
    ]
    resp = client.put(f"/api/transactions/{tx.id}/allocations", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "A transaction can have at most one allocation per company/entity. Manage sub-categories directly in Wave."


def test_update_allocations_rejects_duplicate_personal(client, auth_headers, db_session):
    tx = Transaction(
        source="MANUAL",
        date=date(2026, 10, 20),
        description="Duplicate Personal Test",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("100.00"),
        is_personal=True,
    )
    db_session.add(alloc)
    db_session.commit()

    payload = [
        {"amount": "50.00", "is_personal": True},
        {"amount": "50.00", "is_personal": True},
    ]
    resp = client.put(f"/api/transactions/{tx.id}/allocations", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "A transaction can have at most one allocation per company/entity. Manage sub-categories directly in Wave."


def test_update_allocations_allows_personal_and_business_split(client, auth_headers, db_session):
    company = Company(name="Entity Corp B")
    db_session.add(company)
    db_session.commit()

    tx = Transaction(
        source="MANUAL",
        date=date(2026, 10, 20),
        description="Mixed Personal Business Split",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("100.00"),
        is_personal=False,
        company_id=company.id,
    )
    db_session.add(alloc)
    db_session.commit()

    payload = [
        {"amount": "40.00", "is_personal": True},
        {"amount": "60.00", "is_personal": False, "company_id": str(company.id)},
    ]
    resp = client.put(f"/api/transactions/{tx.id}/allocations", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    allocations = resp.json()
    assert len(allocations) == 2
    personal = next(a for a in allocations if a["is_personal"] is True)
    assert personal["amount"] == "40.00"
    business = next(a for a in allocations if a["is_personal"] is False)
    assert business["amount"] == "60.00"
    assert business["company_id"] == str(company.id)


def test_update_allocations_allows_distinct_companies_split(client, auth_headers, db_session):
    comp1 = Company(name="Entity Corp C1")
    comp2 = Company(name="Entity Corp C2")
    db_session.add_all([comp1, comp2])
    db_session.commit()

    tx = Transaction(
        source="MANUAL",
        date=date(2026, 10, 20),
        description="Multi-Company Split",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("100.00"),
        is_personal=False,
        company_id=comp1.id,
    )
    db_session.add(alloc)
    db_session.commit()

    payload = [
        {"amount": "30.00", "is_personal": False, "company_id": str(comp1.id)},
        {"amount": "70.00", "is_personal": False, "company_id": str(comp2.id)},
    ]
    resp = client.put(f"/api/transactions/{tx.id}/allocations", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    allocations = resp.json()
    assert len(allocations) == 2


def test_create_transaction_rejects_duplicate_company_allocations(client, auth_headers, db_session):
    company = Company(name="Entity Corp D")
    db_session.add(company)
    db_session.commit()

    payload = {
        "source": "MANUAL",
        "date": "2026-10-20",
        "description": "Create Duplicate Company",
        "total_amount": "100.00",
        "allocations": [
            {"amount": "50.00", "is_personal": False, "company_id": str(company.id)},
            {"amount": "50.00", "is_personal": False, "company_id": str(company.id)},
        ],
    }
    resp = client.post("/api/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "A transaction can have at most one allocation per company/entity. Manage sub-categories directly in Wave."
