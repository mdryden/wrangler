import datetime
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.company import Company
from models.staged_transaction import StagedTransaction
from models.transaction import Transaction
from services.mcp import stage_transaction

MOCK_ADMIN = "admin"
MOCK_PASSWORD = "admin"
MOCK_SECRET_KEY = "mock-secret-key-that-is-at-least-32-characters-long!"
MOCK_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def set_mock_env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", MOCK_ADMIN)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", MOCK_PASSWORD)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", MOCK_SECRET_KEY)
    monkeypatch.setattr(settings, "JWT_ALGORITHM", MOCK_ALGORITHM)
    monkeypatch.setattr(settings, "RECEIPT_STORAGE_DIR", tmp_path / "receipts")


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
def client(db_session, monkeypatch):
    testing_session_local = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr("services.mcp.SessionLocal", testing_session_local)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_mcp_staging_full_lifecycle(client, db_session, auth_headers):
    # 1. Ingest transaction via MCP stage_transaction
    stage_msg = await stage_transaction(
        source_label="amazon",
        external_id="order-lifecycle-1",
        date="2026-10-18",
        total_amount=79.99,
        description="Wireless Headphones",
        currency_code="CAD",
    )
    assert "Successfully staged transaction" in stage_msg
    assert "[mcp] amazon:order-lifecycle-1" in stage_msg

    # 2. Verify visibility in staging queries
    res_staged = client.get("/api/staging?status=STAGED", headers=auth_headers)
    assert res_staged.status_code == 200
    staged_items = res_staged.json()["items"]
    mcp_item = next((item for item in staged_items if item["external_id"] == "amazon:order-lifecycle-1"), None)
    assert mcp_item is not None
    assert mcp_item["source"] == "mcp"
    assert mcp_item["status"] == "STAGED"
    assert mcp_item["is_ready"] is False
    assert len(mcp_item["allocations"]) == 0
    staged_id = mcp_item["id"]

    # Verify filtering by source=mcp
    res_source_filter = client.get("/api/staging?source=mcp", headers=auth_headers)
    assert res_source_filter.status_code == 200
    source_items = res_source_filter.json()["items"]
    assert any(item["id"] == staged_id for item in source_items)

    # 3. User allocation assignment: mark record as ready
    company = Company(id=uuid.uuid4(), name="Acme Logistics")
    db_session.add(company)
    db_session.commit()

    put_payload = {
        "allocations": [
            {
                "amount": "79.99",
                "is_personal": False,
                "company_id": str(company.id),
            }
        ]
    }
    res_update = client.put(f"/api/staging/{staged_id}", json=put_payload, headers=auth_headers)
    assert res_update.status_code == 200
    updated_data = res_update.json()
    assert updated_data["is_ready"] is True
    assert len(updated_data["allocations"]) == 1

    # 4. Batch acceptance: accept into ledger
    accept_payload = {"staged_ids": [staged_id]}
    res_accept = client.post("/api/staging/accept", json=accept_payload, headers=auth_headers)
    assert res_accept.status_code == 200
    accept_data = res_accept.json()
    assert accept_data["accepted_count"] == 1
    assert len(accept_data["ledger_transaction_ids"]) == 1

    # Verify record in StagedTransaction is now ACCEPTED
    staged_record = db_session.query(StagedTransaction).filter(StagedTransaction.id == uuid.UUID(staged_id)).first()
    assert staged_record.status == "ACCEPTED"

    # Verify record in Ledger Transaction exists
    ledger_record = db_session.query(Transaction).filter(Transaction.external_id == "amazon:order-lifecycle-1").first()
    assert ledger_record is not None
    assert ledger_record.source == "mcp"
    assert len(ledger_record.allocations) == 1

    # 5. Idempotency after acceptance: re-calling stage_transaction returns skipped response
    re_stage_accepted = await stage_transaction(
        source_label="amazon",
        external_id="order-lifecycle-1",
        date="2026-10-18",
        total_amount=79.99,
        description="Wireless Headphones",
        currency_code="CAD",
    )
    assert re_stage_accepted == "Transaction '[mcp] amazon:order-lifecycle-1' already exists in Wrangler (status: ACCEPTED). Skipped."


@pytest.mark.anyio
async def test_mcp_staging_dismissal_and_idempotency(client, db_session, auth_headers):
    # Ingest a second transaction for dismissal testing
    await stage_transaction(
        source_label="amazon",
        external_id="order-lifecycle-2",
        date="2026-10-19",
        total_amount=19.99,
        description="Phone Case",
    )

    res_staged = client.get("/api/staging?status=STAGED&source=mcp", headers=auth_headers)
    assert res_staged.status_code == 200
    staged_item = next(item for item in res_staged.json()["items"] if item["external_id"] == "amazon:order-lifecycle-2")
    staged_id = staged_item["id"]

    # Dismiss transaction
    res_dismiss = client.post(f"/api/staging/{staged_id}/dismiss", headers=auth_headers)
    assert res_dismiss.status_code == 200
    assert res_dismiss.json()["status"] == "DISMISSED"

    # Verify no longer in STAGED list
    res_staged_after = client.get("/api/staging?status=STAGED&source=mcp", headers=auth_headers)
    assert not any(item["id"] == staged_id for item in res_staged_after.json()["items"])

    # Verify in DISMISSED list
    res_dismissed_list = client.get("/api/staging?status=DISMISSED&source=mcp", headers=auth_headers)
    assert any(item["id"] == staged_id for item in res_dismissed_list.json()["items"])

    # Idempotency after dismissal: re-calling stage_transaction returns skipped response
    re_stage_dismissed = await stage_transaction(
        source_label="amazon",
        external_id="order-lifecycle-2",
        date="2026-10-19",
        total_amount=19.99,
        description="Phone Case",
    )
    assert re_stage_dismissed == "Transaction '[mcp] amazon:order-lifecycle-2' already exists in Wrangler (status: DISMISSED). Skipped."


@pytest.mark.anyio
async def test_mcp_staging_partial_data_completion_and_accept_lifecycle(client, db_session, auth_headers):
    # 1. Ingest partial transaction without date, amount, description
    msg = await stage_transaction(
        source_label="receipts@mmjm.ca",
        external_id="partial-lifecycle-1",
    )
    assert "Needs review in Wrangler: date, total_amount, description." in msg

    # 2. Verify in staging list - not ready
    res_staged = client.get("/api/staging?status=STAGED&source=mcp", headers=auth_headers)
    assert res_staged.status_code == 200
    staged_item = next(item for item in res_staged.json()["items"] if item["external_id"] == "receipts@mmjm.ca:partial-lifecycle-1")
    staged_id = staged_item["id"]
    assert staged_item["date"] is None
    assert staged_item["total_amount"] is None
    assert staged_item["description"] is None
    assert staged_item["is_ready"] is False

    # 3. Acceptance blocked while metadata incomplete
    res_accept_blocked = client.post(
        "/api/staging/accept",
        json={"staged_transaction_ids": [staged_id]},
        headers=auth_headers,
    )
    assert res_accept_blocked.status_code == 400
    assert "not ready for acceptance" in res_accept_blocked.json()["detail"].lower()

    # 4. Update metadata in Wrangler
    res_update = client.put(
        f"/api/staging/{staged_id}",
        json={
            "date": "2026-10-20",
            "total_amount": "50.00",
            "description": "[receipts@mmjm.ca] Completed Office Supplies",
            "allocations": [{"amount": "50.00", "is_personal": True}],
        },
        headers=auth_headers,
    )
    assert res_update.status_code == 200
    updated_data = res_update.json()
    assert updated_data["date"] == "2026-10-20"
    assert updated_data["total_amount"] == "50.00"
    assert updated_data["description"] == "[receipts@mmjm.ca] Completed Office Supplies"
    assert updated_data["is_ready"] is True

    # 5. Acceptance succeeds once complete
    res_accept = client.post(
        "/api/staging/accept",
        json={"staged_transaction_ids": [staged_id]},
        headers=auth_headers,
    )
    assert res_accept.status_code == 200
    assert res_accept.json()["accepted_count"] == 1

    # 6. Verify in live ledger
    ledger_tx = db_session.query(Transaction).filter(Transaction.external_id == "receipts@mmjm.ca:partial-lifecycle-1").first()
    assert ledger_tx is not None
    assert ledger_tx.date == datetime.date(2026, 10, 20)
    assert ledger_tx.total_amount == Decimal("50.00")
    assert ledger_tx.description == "[receipts@mmjm.ca] Completed Office Supplies"
