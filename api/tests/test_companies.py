import csv
import io
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.allocation import Allocation, SyncStatus
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


def test_companies_unauthenticated_requests_blocked(client):
    random_id = uuid.uuid4()
    assert client.get("/api/companies").status_code == 401
    assert client.post("/api/companies", json={"name": "X"}).status_code == 401
    assert client.get(f"/api/companies/{random_id}").status_code == 401
    assert client.put(f"/api/companies/{random_id}", json={"name": "Y"}).status_code == 401
    assert client.delete(f"/api/companies/{random_id}").status_code == 401


def test_create_company_success(client, auth_headers, db_session):
    payload = {
        "name": "Acme Corporation",
    }
    response = client.post("/api/companies", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Acme Corporation"
    assert "id" in data
    assert "wave_equity_account_id" not in data
    assert "wave_business_id" not in data
    assert "is_connected" not in data

    # Check persistence in db
    company_id = uuid.UUID(data["id"])
    db_company = db_session.get(Company, company_id)
    assert db_company is not None
    assert db_company.name == "Acme Corporation"


def test_create_company_duplicate_name_conflict(client, auth_headers):
    client.post("/api/companies", json={"name": "Duplicate Corp"}, headers=auth_headers)
    res = client.post("/api/companies", json={"name": "Duplicate Corp"}, headers=auth_headers)
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]


def test_create_company_validation_error(client, auth_headers):
    # Missing name
    res1 = client.post(
        "/api/companies",
        json={},
        headers=auth_headers,
    )
    assert res1.status_code == 422

    # Empty name
    res2 = client.post(
        "/api/companies",
        json={"name": ""},
        headers=auth_headers,
    )
    assert res2.status_code == 422


def test_list_companies(client, auth_headers):
    # Initially empty
    res = client.get("/api/companies", headers=auth_headers)
    assert res.status_code == 200
    assert res.json() == []

    # Create two companies
    client.post(
        "/api/companies",
        json={"name": "Beta Enterprises"},
        headers=auth_headers,
    )
    client.post(
        "/api/companies",
        json={"name": "Alpha Solutions"},
        headers=auth_headers,
    )

    res = client.get("/api/companies", headers=auth_headers)
    assert res.status_code == 200
    names = [c["name"] for c in res.json()]
    assert names == ["Alpha Solutions", "Beta Enterprises"]


def test_get_company_by_id(client, auth_headers):
    create_res = client.post(
        "/api/companies",
        json={"name": "Sole Proprietor"},
        headers=auth_headers,
    )
    company_id = create_res.json()["id"]

    # Success
    res = client.get(f"/api/companies/{company_id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["id"] == company_id
    assert res.json()["name"] == "Sole Proprietor"

    # Not found
    non_existent = uuid.uuid4()
    res_nf = client.get(f"/api/companies/{non_existent}", headers=auth_headers)
    assert res_nf.status_code == 404


def test_update_company(client, auth_headers, db_session):
    create_res = client.post(
        "/api/companies",
        json={"name": "Original Name"},
        headers=auth_headers,
    )
    company_id = create_res.json()["id"]

    # Partial update
    update_res = client.put(
        f"/api/companies/{company_id}",
        json={"name": "Updated Name"},
        headers=auth_headers,
    )
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["name"] == "Updated Name"

    # Verify in DB
    db_company = db_session.get(Company, uuid.UUID(company_id))
    assert db_company.name == "Updated Name"

    # Update to duplicate name
    client.post("/api/companies", json={"name": "Other Company"}, headers=auth_headers)
    dup_res = client.put(
        f"/api/companies/{company_id}",
        json={"name": "Other Company"},
        headers=auth_headers,
    )
    assert dup_res.status_code == 409

    # Update not found
    non_existent = uuid.uuid4()
    nf_res = client.put(
        f"/api/companies/{non_existent}",
        json={"name": "Does Not Exist"},
        headers=auth_headers,
    )
    assert nf_res.status_code == 404


def test_delete_company(client, auth_headers, db_session):
    create_res = client.post(
        "/api/companies",
        json={"name": "To Delete"},
        headers=auth_headers,
    )
    company_id = create_res.json()["id"]

    # Delete existing
    del_res = client.delete(f"/api/companies/{company_id}", headers=auth_headers)
    assert del_res.status_code == 204

    # Verify deleted
    get_res = client.get(f"/api/companies/{company_id}", headers=auth_headers)
    assert get_res.status_code == 404
    assert db_session.get(Company, uuid.UUID(company_id)) is None

    # Delete non-existent
    del_nf = client.delete(f"/api/companies/{company_id}", headers=auth_headers)
    assert del_nf.status_code == 404


def test_delete_company_blocked_when_linked_to_allocations(client, auth_headers, db_session):
    # Create company
    create_res = client.post(
        "/api/companies",
        json={"name": "Linked Company"},
        headers=auth_headers,
    )
    company_id = uuid.UUID(create_res.json()["id"])

    # Create transaction and allocation linked to company
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Office Expense",
        total_amount=Decimal("150.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("150.00"),
        is_personal=False,
        company_id=company_id,
    )
    db_session.add(alloc)
    db_session.commit()

    # Attempt to delete company
    del_res = client.delete(f"/api/companies/{company_id}", headers=auth_headers)
    assert del_res.status_code == 400
    assert "linked to existing allocations" in del_res.json()["detail"]

    # Verify company still exists
    db_company = db_session.get(Company, company_id)
    assert db_company is not None


def test_export_transactions_unauthenticated(client):
    cid = uuid.uuid4()
    resp = client.get(f"/api/companies/{cid}/export-transactions")
    assert resp.status_code == 401


def test_export_transactions_not_found(client, auth_headers):
    cid = uuid.uuid4()
    resp = client.get(f"/api/companies/{cid}/export-transactions", headers=auth_headers)
    assert resp.status_code == 404


def test_export_transactions_pending_default(client, auth_headers, db_session):
    company1 = Company(name="Alpha Corp")
    company2 = Company(name="Beta LLC")
    db_session.add_all([company1, company2])
    db_session.flush()

    t1 = Transaction(
        source="manual",
        date=date(2026, 9, 1),
        description="Printer, ink & supplies",
        total_amount=Decimal("120.00"),
    )
    t2 = Transaction(
        source="manual",
        date=date(2026, 9, 2),
        description="Software subscription",
        total_amount=Decimal("45.00"),
    )
    db_session.add_all([t1, t2])
    db_session.flush()

    # Company 1 PENDING allocation
    a1 = Allocation(
        transaction_id=t1.id,
        company_id=company1.id,
        amount=Decimal("120.00"),
        is_personal=False,
        sync_status=SyncStatus.PENDING,
    )
    # Company 1 SYNCED allocation (should NOT be exported by default)
    a2 = Allocation(
        transaction_id=t2.id,
        company_id=company1.id,
        amount=Decimal("45.00"),
        is_personal=False,
        sync_status=SyncStatus.SYNCED,
    )
    # Company 1 PERSONAL allocation (should NOT be exported)
    a3 = Allocation(
        transaction_id=t2.id,
        company_id=company1.id,
        amount=Decimal("15.00"),
        is_personal=True,
        sync_status=SyncStatus.PENDING,
    )
    # Company 2 PENDING allocation (should NOT be exported)
    a4 = Allocation(
        transaction_id=t1.id,
        company_id=company2.id,
        amount=Decimal("50.00"),
        is_personal=False,
        sync_status=SyncStatus.PENDING,
    )
    db_session.add_all([a1, a2, a3, a4])
    db_session.commit()

    resp = client.get(f"/api/companies/{company1.id}/export-transactions", headers=auth_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert 'attachment; filename="alpha_corp_pending_transactions.csv"' in resp.headers["content-disposition"]

    reader = list(csv.reader(io.StringIO(resp.text)))
    assert len(reader) == 2
    assert reader[0] == ["Date", "Description", "Amount"]
    assert reader[1] == ["2026-09-01", "Printer, ink & supplies", "120.00"]


def test_export_transactions_synced_status(client, auth_headers, db_session):
    company = Company(name="Gamma Inc")
    db_session.add(company)
    db_session.flush()

    tx = Transaction(
        source="manual",
        date=date(2026, 9, 3),
        description="Consulting fee",
        total_amount=Decimal("500.00"),
    )
    db_session.add(tx)
    db_session.flush()

    alloc = Allocation(
        transaction_id=tx.id,
        company_id=company.id,
        amount=Decimal("500.00"),
        is_personal=False,
        sync_status=SyncStatus.SYNCED,
    )
    db_session.add(alloc)
    db_session.commit()

    resp = client.get(f"/api/companies/{company.id}/export-transactions?status=SYNCED", headers=auth_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert 'attachment; filename="gamma_inc_synced_transactions.csv"' in resp.headers["content-disposition"]

    reader = list(csv.reader(io.StringIO(resp.text)))
    assert len(reader) == 2
    assert reader[0] == ["Date", "Description", "Amount"]
    assert reader[1] == ["2026-09-03", "Consulting fee", "500.00"]


def test_mark_synced_unauthenticated(client):
    cid = uuid.uuid4()
    resp = client.post(f"/api/companies/{cid}/mark-synced")
    assert resp.status_code == 401


def test_mark_synced_not_found(client, auth_headers):
    cid = uuid.uuid4()
    resp = client.post(f"/api/companies/{cid}/mark-synced", headers=auth_headers)
    assert resp.status_code == 404


def test_mark_synced_all_pending_when_omitted_payload(client, auth_headers, db_session):
    company1 = Company(name="Sync Test Corp 1")
    company2 = Company(name="Sync Test Corp 2")
    db_session.add_all([company1, company2])
    db_session.flush()

    tx = Transaction(
        source="manual",
        date=date(2026, 9, 1),
        description="Sync Test Tx",
        total_amount=Decimal("300.00"),
    )
    db_session.add(tx)
    db_session.flush()

    a1 = Allocation(
        transaction_id=tx.id,
        company_id=company1.id,
        amount=Decimal("100.00"),
        is_personal=False,
        sync_status=SyncStatus.PENDING,
    )
    a2 = Allocation(
        transaction_id=tx.id,
        company_id=company1.id,
        amount=Decimal("100.00"),
        is_personal=False,
        sync_status=SyncStatus.PENDING,
    )
    # Personal allocation (should remain PENDING)
    a3 = Allocation(
        transaction_id=tx.id,
        company_id=company1.id,
        amount=Decimal("50.00"),
        is_personal=True,
        sync_status=SyncStatus.PENDING,
    )
    # Another company allocation (should remain PENDING)
    a4 = Allocation(
        transaction_id=tx.id,
        company_id=company2.id,
        amount=Decimal("50.00"),
        is_personal=False,
        sync_status=SyncStatus.PENDING,
    )
    db_session.add_all([a1, a2, a3, a4])
    db_session.commit()

    # Call mark-synced with no payload body
    resp = client.post(f"/api/companies/{company1.id}/mark-synced", headers=auth_headers)
    assert resp.status_code == 200
    res_data = resp.json()
    assert len(res_data) == 2
    assert {item["id"] for item in res_data} == {str(a1.id), str(a2.id)}
    assert all(item["sync_status"] == SyncStatus.SYNCED for item in res_data)

    db_session.expire_all()
    assert db_session.get(Allocation, a1.id).sync_status == SyncStatus.SYNCED
    assert db_session.get(Allocation, a2.id).sync_status == SyncStatus.SYNCED
    assert db_session.get(Allocation, a3.id).sync_status == SyncStatus.PENDING
    assert db_session.get(Allocation, a4.id).sync_status == SyncStatus.PENDING


def test_mark_synced_specific_allocations(client, auth_headers, db_session):
    company = Company(name="Specific Sync Corp")
    db_session.add(company)
    db_session.flush()

    tx = Transaction(
        source="manual",
        date=date(2026, 9, 2),
        description="Tx for specific sync",
        total_amount=Decimal("200.00"),
    )
    db_session.add(tx)
    db_session.flush()

    a1 = Allocation(
        transaction_id=tx.id,
        company_id=company.id,
        amount=Decimal("100.00"),
        is_personal=False,
        sync_status=SyncStatus.PENDING,
    )
    a2 = Allocation(
        transaction_id=tx.id,
        company_id=company.id,
        amount=Decimal("100.00"),
        is_personal=False,
        sync_status=SyncStatus.PENDING,
    )
    db_session.add_all([a1, a2])
    db_session.commit()

    # Pass only a1.id in allocation_ids
    payload = {"allocation_ids": [str(a1.id)]}
    resp = client.post(f"/api/companies/{company.id}/mark-synced", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    res_data = resp.json()
    assert len(res_data) == 1
    assert res_data[0]["id"] == str(a1.id)
    assert res_data[0]["sync_status"] == SyncStatus.SYNCED

    db_session.expire_all()
    assert db_session.get(Allocation, a1.id).sync_status == SyncStatus.SYNCED
    assert db_session.get(Allocation, a2.id).sync_status == SyncStatus.PENDING


def test_revert_synced_unauthenticated(client):
    cid = uuid.uuid4()
    resp = client.post(f"/api/companies/{cid}/revert-synced")
    assert resp.status_code == 401


def test_revert_synced_not_found(client, auth_headers):
    cid = uuid.uuid4()
    resp = client.post(f"/api/companies/{cid}/revert-synced", headers=auth_headers)
    assert resp.status_code == 404


def test_revert_synced_all_synced_when_omitted_payload(client, auth_headers, db_session):
    company1 = Company(name="Revert Test Corp 1")
    company2 = Company(name="Revert Test Corp 2")
    db_session.add_all([company1, company2])
    db_session.flush()

    tx = Transaction(
        source="manual",
        date=date(2026, 9, 1),
        description="Revert Test Tx",
        total_amount=Decimal("300.00"),
    )
    db_session.add(tx)
    db_session.flush()

    a1 = Allocation(
        transaction_id=tx.id,
        company_id=company1.id,
        amount=Decimal("100.00"),
        is_personal=False,
        sync_status=SyncStatus.SYNCED,
    )
    a2 = Allocation(
        transaction_id=tx.id,
        company_id=company1.id,
        amount=Decimal("100.00"),
        is_personal=False,
        sync_status=SyncStatus.SYNCED,
    )
    # Personal allocation (should remain SYNCED)
    a3 = Allocation(
        transaction_id=tx.id,
        company_id=company1.id,
        amount=Decimal("50.00"),
        is_personal=True,
        sync_status=SyncStatus.SYNCED,
    )
    # Another company allocation (should remain SYNCED)
    a4 = Allocation(
        transaction_id=tx.id,
        company_id=company2.id,
        amount=Decimal("50.00"),
        is_personal=False,
        sync_status=SyncStatus.SYNCED,
    )
    db_session.add_all([a1, a2, a3, a4])
    db_session.commit()

    # Call revert-synced with no payload body
    resp = client.post(f"/api/companies/{company1.id}/revert-synced", headers=auth_headers)
    assert resp.status_code == 200
    res_data = resp.json()
    assert len(res_data) == 2
    assert {item["id"] for item in res_data} == {str(a1.id), str(a2.id)}
    assert all(item["sync_status"] == SyncStatus.PENDING for item in res_data)

    db_session.expire_all()
    assert db_session.get(Allocation, a1.id).sync_status == SyncStatus.PENDING
    assert db_session.get(Allocation, a2.id).sync_status == SyncStatus.PENDING
    assert db_session.get(Allocation, a3.id).sync_status == SyncStatus.SYNCED
    assert db_session.get(Allocation, a4.id).sync_status == SyncStatus.SYNCED


def test_revert_synced_specific_allocations(client, auth_headers, db_session):
    company = Company(name="Specific Revert Corp")
    db_session.add(company)
    db_session.flush()

    tx = Transaction(
        source="manual",
        date=date(2026, 9, 2),
        description="Tx for specific revert",
        total_amount=Decimal("200.00"),
    )
    db_session.add(tx)
    db_session.flush()

    a1 = Allocation(
        transaction_id=tx.id,
        company_id=company.id,
        amount=Decimal("100.00"),
        is_personal=False,
        sync_status=SyncStatus.SYNCED,
    )
    a2 = Allocation(
        transaction_id=tx.id,
        company_id=company.id,
        amount=Decimal("100.00"),
        is_personal=False,
        sync_status=SyncStatus.SYNCED,
    )
    db_session.add_all([a1, a2])
    db_session.commit()

    # Pass only a1.id in allocation_ids
    payload = {"allocation_ids": [str(a1.id)]}
    resp = client.post(f"/api/companies/{company.id}/revert-synced", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    res_data = resp.json()
    assert len(res_data) == 1
    assert res_data[0]["id"] == str(a1.id)
    assert res_data[0]["sync_status"] == SyncStatus.PENDING

    db_session.expire_all()
    assert db_session.get(Allocation, a1.id).sync_status == SyncStatus.PENDING
    assert db_session.get(Allocation, a2.id).sync_status == SyncStatus.SYNCED


def test_list_and_get_companies_transaction_count(client, auth_headers, db_session):
    c1 = Company(name="Count Co 1")
    c2 = Company(name="Count Co 2")
    db_session.add_all([c1, c2])
    db_session.commit()

    tx1 = Transaction(
        source="manual",
        external_id="count-tx-1",
        date=date.today(),
        description="Tx 1",
        total_amount=Decimal("150.00"),
    )
    tx2 = Transaction(
        source="manual",
        external_id="count-tx-2",
        date=date.today(),
        description="Tx 2",
        total_amount=Decimal("50.00"),
    )
    db_session.add_all([tx1, tx2])
    db_session.commit()

    # 2 allocations for c1 across 2 different transactions
    alloc1 = Allocation(
        transaction_id=tx1.id,
        company_id=c1.id,
        amount=Decimal("100.00"),
        is_personal=False,
    )
    alloc2 = Allocation(
        transaction_id=tx2.id,
        company_id=c1.id,
        amount=Decimal("50.00"),
        is_personal=False,
    )
    # Personal allocation for tx1 shouldn't count
    alloc_personal = Allocation(
        transaction_id=tx1.id,
        company_id=None,
        amount=Decimal("50.00"),
        is_personal=True,
    )
    db_session.add_all([alloc1, alloc2, alloc_personal])
    db_session.commit()

    # List companies
    res = client.get("/api/companies", headers=auth_headers)
    assert res.status_code == 200
    data = {c["name"]: c["transaction_count"] for c in res.json()}
    assert data["Count Co 1"] == 2
    assert data["Count Co 2"] == 0

    # Get single company
    res_c1 = client.get(f"/api/companies/{c1.id}", headers=auth_headers)
    assert res_c1.status_code == 200
    assert res_c1.json()["transaction_count"] == 2

    res_c2 = client.get(f"/api/companies/{c2.id}", headers=auth_headers)
    assert res_c2.status_code == 200
    assert res_c2.json()["transaction_count"] == 0
