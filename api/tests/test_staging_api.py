import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from core.security import create_access_token
from database import get_db
from main import app
from models.company import Company
from models.staged_allocation import StagedAllocation
from models.staged_transaction import StagedTransaction
from models.transaction import Transaction
from services.importers.base import BaseImporter, ImportedTransactionData, ImporterInputType
from services.importers.registry import _IMPORTERS_BY_ID, register_importer

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


class MarkableTestImporter(BaseImporter):
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.marked_batches: list[list[str]] = []

    @property
    def importer_id(self) -> str:
        return "markable_source"

    @property
    def display_name(self) -> str:
        return "Markable Source"

    @property
    def description(self) -> str:
        return "Importer that supports marking imported"

    @property
    def input_type(self) -> ImporterInputType:
        return ImporterInputType.NONE

    @property
    def supports_mark_imported(self) -> bool:
        return True

    async def fetch_and_parse(
        self,
        file_bytes: bytes | None = None,
        filename: str | None = None,
    ) -> list[ImportedTransactionData]:
        return []

    async def mark_as_imported(self, external_ids: list[str]) -> None:
        if self.should_fail:
            raise RuntimeError("External API timeout")
        self.marked_batches.append(list(external_ids))


@pytest.fixture
def markable_importer():
    saved = dict(_IMPORTERS_BY_ID)
    _IMPORTERS_BY_ID.clear()
    imp = MarkableTestImporter()
    register_importer(imp)
    try:
        yield imp
    finally:
        _IMPORTERS_BY_ID.clear()
        _IMPORTERS_BY_ID.update(saved)


def test_staging_unauthenticated_blocked(client):
    sid = uuid.uuid4()
    assert client.get("/api/staging").status_code == 401
    assert client.put(f"/api/staging/{sid}", json={}).status_code == 401
    assert client.post(f"/api/staging/{sid}/receipt").status_code == 401
    assert client.delete(f"/api/staging/{sid}/receipt").status_code == 401
    assert client.post(f"/api/staging/{sid}/dismiss").status_code == 401
    assert client.post(f"/api/staging/{sid}/restore").status_code == 401
    assert client.post("/api/staging/accept").status_code == 401
    assert client.post("/api/staging/bulk-allocate", json={"staged_transaction_ids": [str(sid)], "clear": True}).status_code == 401
    assert client.post("/api/staging/bulk-dismiss", json={"staged_transaction_ids": [str(sid)]}).status_code == 401


def test_list_staged_transactions_filtering_and_pagination(client, auth_headers, db_session, markable_importer):
    st1 = StagedTransaction(
        source="markable_source",
        external_id="S-1",
        date=date(2026, 10, 1),
        description="Older staged",
        total_amount=Decimal("20.00"),
        url="https://amazon.ca/orders/S-1",
        status="STAGED",
    )
    st2 = StagedTransaction(
        source="csv_source",
        external_id="S-2",
        date=date(2026, 10, 5),
        description="Newer staged",
        total_amount=Decimal("40.00"),
        status="STAGED",
    )
    st3 = StagedTransaction(
        source="csv_source",
        external_id="S-3",
        date=date(2026, 10, 3),
        description="Dismissed item",
        total_amount=Decimal("60.00"),
        status="DISMISSED",
    )
    db_session.add_all([st1, st2, st3])
    db_session.commit()

    # Default filter: status=STAGED ordered by date DESC
    res = client.get("/api/staging", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["description"] == "Newer staged"
    assert data["items"][0]["url"] is None
    assert data["items"][0]["supports_mark_imported"] is False
    assert data["items"][1]["description"] == "Older staged"
    assert data["items"][1]["url"] == "https://amazon.ca/orders/S-1"
    assert data["items"][1]["supports_mark_imported"] is True

    # Filter by status=DISMISSED
    res_dis = client.get("/api/staging?status=DISMISSED", headers=auth_headers)
    assert res_dis.status_code == 200
    assert res_dis.json()["total"] == 1
    assert res_dis.json()["items"][0]["description"] == "Dismissed item"

    # Filter by source & pagination
    res_src = client.get("/api/staging?status=STAGED&source=markable_source&page=1&page_size=1", headers=auth_headers)
    assert res_src.status_code == 200
    assert res_src.json()["total"] == 1
    assert res_src.json()["items"][0]["external_id"] == "S-1"


def test_update_staged_transaction_metadata_and_allocations(client, auth_headers, db_session):
    c1 = Company(name="Company One")
    c2 = Company(name="Company Two")
    db_session.add_all([c1, c2])
    db_session.commit()

    stx = StagedTransaction(
        source="csv_source",
        external_id="U-1",
        date=date(2026, 10, 1),
        description="Original Desc",
        total_amount=Decimal("100.00"),
        status="STAGED",
    )
    db_session.add(stx)
    db_session.commit()

    # 1. Assign single business allocation
    res_bus = client.put(
        f"/api/staging/{stx.id}",
        json={
            "description": "Updated Business Desc",
            "allocations": [{"amount": "100.00", "is_personal": False, "company_id": str(c1.id)}],
        },
        headers=auth_headers,
    )
    assert res_bus.status_code == 200
    body_bus = res_bus.json()
    assert body_bus["description"] == "Updated Business Desc"
    assert body_bus["is_ready"] is True
    assert len(body_bus["allocations"]) == 1
    assert body_bus["allocations"][0]["company_id"] == str(c1.id)

    # 2. Assign single personal allocation
    res_pers = client.put(
        f"/api/staging/{stx.id}",
        json={
            "allocations": [{"amount": "100.00", "is_personal": True}],
        },
        headers=auth_headers,
    )
    assert res_pers.status_code == 200
    assert res_pers.json()["is_ready"] is True
    assert res_pers.json()["allocations"][0]["is_personal"] is True
    assert res_pers.json()["allocations"][0]["company_id"] is None

    # 3. Assign multi-company split and update total_amount
    res_split = client.put(
        f"/api/staging/{stx.id}",
        json={
            "total_amount": "150.00",
            "allocations": [
                {"amount": "90.00", "is_personal": False, "company_id": str(c1.id)},
                {"amount": "60.00", "is_personal": False, "company_id": str(c2.id)},
            ],
        },
        headers=auth_headers,
    )
    assert res_split.status_code == 200
    assert res_split.json()["is_ready"] is True
    assert len(res_split.json()["allocations"]) == 2

    # 4. Clear allocations with empty list [] -> resets is_ready to False
    res_clear = client.put(
        f"/api/staging/{stx.id}",
        json={"allocations": []},
        headers=auth_headers,
    )
    assert res_clear.status_code == 200
    assert res_clear.json()["allocations"] == []
    assert res_clear.json()["is_ready"] is False

    # 5. URL update and clear
    res_url = client.put(
        f"/api/staging/{stx.id}",
        json={"url": "https://amazon.ca/orders/U-1"},
        headers=auth_headers,
    )
    assert res_url.status_code == 200
    assert res_url.json()["url"] == "https://amazon.ca/orders/U-1"

    # URL update with whitespace clears to None
    res_url_ws = client.put(
        f"/api/staging/{stx.id}",
        json={"url": "   "},
        headers=auth_headers,
    )
    assert res_url_ws.status_code == 200
    assert res_url_ws.json()["url"] is None

    # URL update to another URL
    res_url_2 = client.put(
        f"/api/staging/{stx.id}",
        json={"url": "https://amazon.ca/orders/U-2"},
        headers=auth_headers,
    )
    assert res_url_2.status_code == 200
    assert res_url_2.json()["url"] == "https://amazon.ca/orders/U-2"

    # URL update to None clears to None
    res_url_none = client.put(
        f"/api/staging/{stx.id}",
        json={"url": None},
        headers=auth_headers,
    )
    assert res_url_none.status_code == 200
    assert res_url_none.json()["url"] is None

    # 6. Validation errors: unbalanced sum, personal in multi-split, unknown company
    res_unbal = client.put(
        f"/api/staging/{stx.id}",
        json={"allocations": [{"amount": "10.00", "is_personal": True}]},
        headers=auth_headers,
    )
    assert res_unbal.status_code == 400

    res_pers_split = client.put(
        f"/api/staging/{stx.id}",
        json={
            "allocations": [
                {"amount": "100.00", "is_personal": False, "company_id": str(c1.id)},
                {"amount": "50.00", "is_personal": True},
            ]
        },
        headers=auth_headers,
    )
    assert res_pers_split.status_code == 400

    res_bad_co = client.put(
        f"/api/staging/{stx.id}",
        json={
            "allocations": [
                {"amount": "150.00", "is_personal": False, "company_id": str(uuid.uuid4())},
            ]
        },
        headers=auth_headers,
    )
    assert res_bad_co.status_code == 400


def test_staged_receipt_upload_replace_and_delete(client, auth_headers, db_session):
    c1 = Company(name="Receipt Co")
    db_session.add(c1)
    db_session.commit()

    stx = StagedTransaction(
        source="csv_source",
        external_id="R-1",
        date=date(2026, 10, 1),
        description="Receipt test",
        total_amount=Decimal("50.00"),
        status="STAGED",
    )
    db_session.add(stx)
    db_session.commit()

    # Upload via POST /api/staging/{id}/receipt
    res_up = client.post(
        f"/api/staging/{stx.id}/receipt",
        files={"file": ("first.pdf", b"%PDF-1.4 first", "application/pdf")},
        headers=auth_headers,
    )
    assert res_up.status_code == 200
    first_path = res_up.json()["receipt_file_path"]
    assert first_path is not None
    assert (settings.RECEIPT_STORAGE_DIR / first_path).is_file()

    # Replace receipt and update allocations via multipart PUT /api/staging/{id}
    res_put = client.put(
        f"/api/staging/{stx.id}",
        data={
            "description": "Multipart Updated",
            "allocations": json.dumps([{"amount": "50.00", "is_personal": False, "company_id": str(c1.id)}]),
        },
        files={"file": ("second.pdf", b"%PDF-1.4 second", "application/pdf")},
        headers=auth_headers,
    )
    assert res_put.status_code == 200
    second_path = res_put.json()["receipt_file_path"]
    assert second_path != first_path
    assert not (settings.RECEIPT_STORAGE_DIR / first_path).exists()
    assert (settings.RECEIPT_STORAGE_DIR / second_path).is_file()
    assert res_put.json()["is_ready"] is True

    # Delete receipt via DELETE /api/staging/{id}/receipt
    res_del = client.delete(f"/api/staging/{stx.id}/receipt", headers=auth_headers)
    assert res_del.status_code == 200
    assert res_del.json()["receipt_file_path"] is None
    assert not (settings.RECEIPT_STORAGE_DIR / second_path).exists()


def test_dismiss_and_restore_staged_transaction(client, auth_headers, db_session, markable_importer):
    c1 = Company(name="Dismiss Co")
    db_session.add(c1)
    db_session.commit()

    settings.RECEIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    receipt_filename = "dismiss_receipt.pdf"
    (settings.RECEIPT_STORAGE_DIR / receipt_filename).write_bytes(b"receipt data")

    stx = StagedTransaction(
        source="markable_source",
        external_id="DIS-1",
        date=date(2026, 10, 1),
        description="To dismiss",
        total_amount=Decimal("30.00"),
        receipt_file_path=receipt_filename,
        status="STAGED",
    )
    db_session.add(stx)
    db_session.commit()

    s_alloc = StagedAllocation(
        staged_transaction_id=stx.id,
        amount=Decimal("30.00"),
        is_personal=False,
        company_id=c1.id,
    )
    db_session.add(s_alloc)
    db_session.commit()

    # Dismiss -> clears allocations, deletes receipt file, sets DISMISSED, and calls mark_as_imported
    res_dis = client.post(f"/api/staging/{stx.id}/dismiss", headers=auth_headers)
    assert res_dis.status_code == 200
    dis_body = res_dis.json()
    assert dis_body["status"] == "DISMISSED"
    assert dis_body["allocations"] == []
    assert dis_body["receipt_file_path"] is None
    assert dis_body["is_marked_imported"] is True
    assert dis_body["mark_imported_error"] is None
    assert not (settings.RECEIPT_STORAGE_DIR / receipt_filename).exists()
    assert markable_importer.marked_batches == [["DIS-1"]]

    # Cannot dismiss when already DISMISSED
    assert client.post(f"/api/staging/{stx.id}/dismiss", headers=auth_headers).status_code == 400

    # Restore -> sets STAGED with zero allocations and preserves is_marked_imported
    res_rest = client.post(f"/api/staging/{stx.id}/restore", headers=auth_headers)
    assert res_rest.status_code == 200
    rest_body = res_rest.json()
    assert rest_body["status"] == "STAGED"
    assert rest_body["allocations"] == []
    assert rest_body["is_ready"] is False
    assert rest_body["is_marked_imported"] is True

    # Cannot restore when already STAGED
    assert client.post(f"/api/staging/{stx.id}/restore", headers=auth_headers).status_code == 400


def test_dismiss_mark_as_imported_error_resilience(client, auth_headers, db_session, markable_importer):
    markable_importer.should_fail = True

    stx = StagedTransaction(
        source="markable_source",
        external_id="DIS-ERR",
        date=date(2026, 10, 1),
        description="Dismiss with external error",
        total_amount=Decimal("25.00"),
        status="STAGED",
    )
    db_session.add(stx)
    db_session.commit()

    res = client.post(f"/api/staging/{stx.id}/dismiss", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "DISMISSED"
    assert body["is_marked_imported"] is False
    assert body["mark_imported_error"] is not None
    assert "External API timeout" in body["mark_imported_error"]


def test_batch_accept_staged_transactions_and_mark_imported_hooks(client, auth_headers, db_session, markable_importer):
    c1 = Company(name="Accept Co 1")
    c2 = Company(name="Accept Co 2")
    db_session.add_all([c1, c2])
    db_session.commit()

    # Ready item 1 (markable source, split allocation)
    st_ready_1 = StagedTransaction(
        source="markable_source",
        external_id="ACC-1",
        date=date(2026, 10, 1),
        description="Ready Split Tx",
        total_amount=Decimal("100.00"),
        url="https://amazon.ca/orders/ACC-1",
        status="STAGED",
    )
    # Ready item 2 (personal allocation)
    st_ready_2 = StagedTransaction(
        source="markable_source",
        external_id="ACC-2",
        date=date(2026, 10, 2),
        description="Ready Personal Tx",
        total_amount=Decimal("45.00"),
        status="STAGED",
    )
    # Unready item (no allocations)
    st_unready = StagedTransaction(
        source="markable_source",
        external_id="ACC-UNREADY",
        date=date(2026, 10, 3),
        description="Unready Tx",
        total_amount=Decimal("80.00"),
        status="STAGED",
    )
    db_session.add_all([st_ready_1, st_ready_2, st_unready])
    db_session.commit()

    db_session.add_all(
        [
            StagedAllocation(staged_transaction_id=st_ready_1.id, amount=Decimal("60.00"), is_personal=False, company_id=c1.id),
            StagedAllocation(staged_transaction_id=st_ready_1.id, amount=Decimal("40.00"), is_personal=False, company_id=c2.id),
            StagedAllocation(staged_transaction_id=st_ready_2.id, amount=Decimal("45.00"), is_personal=True, company_id=None),
        ]
    )
    db_session.commit()

    # 1. Explicit accept containing an unready ID -> 400 Bad Request, nothing accepted
    res_fail = client.post(
        "/api/staging/accept",
        json={"staged_transaction_ids": [str(st_ready_1.id), str(st_unready.id)]},
        headers=auth_headers,
    )
    assert res_fail.status_code == 400
    assert "not ready" in res_fail.json()["detail"]

    # 2. Accept all ready when staged_transaction_ids is omitted -> accepts st_ready_1 and st_ready_2
    res_acc = client.post("/api/staging/accept", json={}, headers=auth_headers)
    assert res_acc.status_code == 200
    acc_body = res_acc.json()
    assert acc_body["accepted_count"] == 2
    assert len(acc_body["ledger_transaction_ids"]) == 2
    assert acc_body["marked_imported_count"] == 2
    assert acc_body["mark_imported_errors"] == []
    assert markable_importer.marked_batches == [["ACC-1", "ACC-2"]]

    # Verify Ledger Transactions and Allocations were created and StagedTransaction rows updated
    db_session.expire_all()
    refreshed_1 = db_session.get(StagedTransaction, st_ready_1.id)
    assert refreshed_1.status == "ACCEPTED"
    assert refreshed_1.is_marked_imported is True
    assert refreshed_1.ledger_transaction_id is not None
    assert refreshed_1.url == "https://amazon.ca/orders/ACC-1"

    ledger_tx_1 = db_session.get(Transaction, refreshed_1.ledger_transaction_id)
    assert ledger_tx_1 is not None
    assert ledger_tx_1.external_id == "ACC-1"
    assert not hasattr(ledger_tx_1, "url")
    assert not hasattr(ledger_tx_1, "currency_code")
    assert len(ledger_tx_1.allocations) == 2
    assert all(not a.is_locked for a in ledger_tx_1.allocations)

    # 3. Verify mark_as_imported error resilience on accept
    markable_importer.should_fail = True
    db_session.add(StagedAllocation(staged_transaction_id=st_unready.id, amount=Decimal("80.00"), is_personal=False, company_id=c1.id))
    db_session.commit()

    res_err_acc = client.post(
        "/api/staging/accept",
        json={"staged_transaction_ids": [str(st_unready.id)]},
        headers=auth_headers,
    )
    assert res_err_acc.status_code == 200
    err_body = res_err_acc.json()
    assert err_body["accepted_count"] == 1
    assert err_body["marked_imported_count"] == 0
    assert len(err_body["mark_imported_errors"]) == 1
    assert "External API timeout" in err_body["mark_imported_errors"][0]

    db_session.expire_all()
    refreshed_3 = db_session.get(StagedTransaction, st_unready.id)
    assert refreshed_3.status == "ACCEPTED"
    assert refreshed_3.is_marked_imported is False
    assert refreshed_3.ledger_transaction_id is not None


def test_bulk_allocate_personal(client, auth_headers, db_session):
    c1 = Company(id=uuid.uuid4(), name="Company A")
    db_session.add(c1)
    st1 = StagedTransaction(
        id=uuid.uuid4(),
        source="csv",
        date=date(2026, 4, 1),
        description="Office Supplies",
        total_amount=Decimal("45.00"),
        status="STAGED",
    )
    st2 = StagedTransaction(
        id=uuid.uuid4(),
        source="csv",
        date=date(2026, 4, 2),
        description="Software Subscription",
        total_amount=Decimal("120.00"),
        status="STAGED",
    )
    db_session.add_all([st1, st2])
    db_session.flush()
    # Add an existing company allocation to st2 to verify replacement
    db_session.add(StagedAllocation(staged_transaction_id=st2.id, amount=Decimal("120.00"), is_personal=False, company_id=c1.id))
    db_session.commit()

    res = client.post(
        "/api/staging/bulk-allocate",
        json={"staged_transaction_ids": [str(st1.id), str(st2.id)], "is_personal": True},
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["updated_count"] == 2
    assert set(body["staged_transaction_ids"]) == {str(st1.id), str(st2.id)}

    db_session.expire_all()
    for st_id, expected_amount in [(st1.id, Decimal("45.00")), (st2.id, Decimal("120.00"))]:
        st = db_session.get(StagedTransaction, st_id)
        assert len(st.allocations) == 1
        alloc = st.allocations[0]
        assert alloc.is_personal is True
        assert alloc.company_id is None
        assert alloc.amount == expected_amount

    # Also verify through GET /api/staging that is_ready is computed as True
    list_res = client.get("/api/staging", headers=auth_headers)
    assert list_res.status_code == 200
    items_by_id = {item["id"]: item for item in list_res.json()["items"]}
    assert items_by_id[str(st1.id)]["is_ready"] is True
    assert items_by_id[str(st2.id)]["is_ready"] is True


def test_bulk_allocate_company(client, auth_headers, db_session):
    c1 = Company(id=uuid.uuid4(), name="Company A")
    db_session.add(c1)
    st1 = StagedTransaction(
        id=uuid.uuid4(),
        source="csv",
        date=date(2026, 4, 3),
        description="Printer Ink",
        total_amount=Decimal("89.99"),
        status="STAGED",
    )
    st2 = StagedTransaction(
        id=uuid.uuid4(),
        source="csv",
        date=date(2026, 4, 4),
        description="Cloud Hosting",
        total_amount=Decimal("250.00"),
        status="STAGED",
    )
    db_session.add_all([st1, st2])
    db_session.commit()

    res = client.post(
        "/api/staging/bulk-allocate",
        json={"staged_transaction_ids": [str(st1.id), str(st2.id)], "company_id": str(c1.id)},
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["updated_count"] == 2

    db_session.expire_all()
    for st_id, expected_amount in [(st1.id, Decimal("89.99")), (st2.id, Decimal("250.00"))]:
        st = db_session.get(StagedTransaction, st_id)
        assert len(st.allocations) == 1
        alloc = st.allocations[0]
        assert alloc.is_personal is False
        assert alloc.company_id == c1.id
        assert alloc.amount == expected_amount

    list_res = client.get("/api/staging", headers=auth_headers)
    items_by_id = {item["id"]: item for item in list_res.json()["items"]}
    assert items_by_id[str(st1.id)]["is_ready"] is True
    assert items_by_id[str(st2.id)]["is_ready"] is True


def test_bulk_allocate_clear(client, auth_headers, db_session):
    c1 = Company(id=uuid.uuid4(), name="Company A")
    db_session.add(c1)
    st = StagedTransaction(
        id=uuid.uuid4(),
        source="csv",
        date=date(2026, 4, 5),
        description="Team Lunch",
        total_amount=Decimal("60.00"),
        status="STAGED",
    )
    db_session.add(st)
    db_session.flush()
    db_session.add(StagedAllocation(staged_transaction_id=st.id, amount=Decimal("60.00"), is_personal=False, company_id=c1.id))
    db_session.commit()

    # Clear allocations
    res = client.post(
        "/api/staging/bulk-allocate",
        json={"staged_transaction_ids": [str(st.id)], "clear": True},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["updated_count"] == 1

    db_session.expire_all()
    refreshed = db_session.get(StagedTransaction, st.id)
    assert len(refreshed.allocations) == 0

    list_res = client.get("/api/staging", headers=auth_headers)
    items_by_id = {item["id"]: item for item in list_res.json()["items"]}
    assert items_by_id[str(st.id)]["is_ready"] is False


def test_bulk_allocate_overwrites_existing_splits(client, auth_headers, db_session):
    c1 = Company(id=uuid.uuid4(), name="Company 1")
    c2 = Company(id=uuid.uuid4(), name="Company 2")
    db_session.add_all([c1, c2])
    st = StagedTransaction(
        id=uuid.uuid4(),
        source="csv",
        date=date(2026, 4, 6),
        description="Shared Equipment",
        total_amount=Decimal("100.00"),
        status="STAGED",
    )
    db_session.add(st)
    db_session.flush()
    # Add two split allocations
    db_session.add(StagedAllocation(staged_transaction_id=st.id, amount=Decimal("60.00"), is_personal=False, company_id=c1.id))
    db_session.add(StagedAllocation(staged_transaction_id=st.id, amount=Decimal("40.00"), is_personal=False, company_id=c2.id))
    db_session.commit()

    res = client.post(
        "/api/staging/bulk-allocate",
        json={"staged_transaction_ids": [str(st.id)], "company_id": str(c1.id)},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["updated_count"] == 1

    db_session.expire_all()
    refreshed = db_session.get(StagedTransaction, st.id)
    assert len(refreshed.allocations) == 1
    assert refreshed.allocations[0].amount == Decimal("100.00")
    assert refreshed.allocations[0].company_id == c1.id


def test_bulk_allocate_skips_non_staged(client, auth_headers, db_session):
    st_staged = StagedTransaction(
        id=uuid.uuid4(),
        source="csv",
        date=date(2026, 4, 7),
        description="Active Staged",
        total_amount=Decimal("25.00"),
        status="STAGED",
    )
    st_accepted = StagedTransaction(
        id=uuid.uuid4(),
        source="csv",
        date=date(2026, 4, 7),
        description="Already Accepted",
        total_amount=Decimal("50.00"),
        status="ACCEPTED",
    )
    st_dismissed = StagedTransaction(
        id=uuid.uuid4(),
        source="csv",
        date=date(2026, 4, 7),
        description="Already Dismissed",
        total_amount=Decimal("75.00"),
        status="DISMISSED",
    )
    db_session.add_all([st_staged, st_accepted, st_dismissed])
    db_session.commit()

    res = client.post(
        "/api/staging/bulk-allocate",
        json={
            "staged_transaction_ids": [str(st_staged.id), str(st_accepted.id), str(st_dismissed.id)],
            "is_personal": True,
        },
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["updated_count"] == 1
    assert body["staged_transaction_ids"] == [str(st_staged.id)]

    db_session.expire_all()
    assert len(db_session.get(StagedTransaction, st_staged.id).allocations) == 1
    assert len(db_session.get(StagedTransaction, st_accepted.id).allocations) == 0
    assert len(db_session.get(StagedTransaction, st_dismissed.id).allocations) == 0


def test_bulk_allocate_validation_errors(client, auth_headers, db_session):
    st = StagedTransaction(
        id=uuid.uuid4(),
        source="csv",
        date=date(2026, 4, 8),
        description="Test Item",
        total_amount=Decimal("30.00"),
        status="STAGED",
    )
    st_no_amount = StagedTransaction(
        id=uuid.uuid4(),
        source="csv",
        date=date(2026, 4, 8),
        description="Missing Amount",
        total_amount=None,
        status="STAGED",
    )
    db_session.add_all([st, st_no_amount])
    db_session.commit()

    # 1. Empty list
    res = client.post(
        "/api/staging/bulk-allocate",
        json={"staged_transaction_ids": [], "is_personal": True},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "staged_transaction_ids must not be empty" in res.json()["detail"]

    # 2. Both personal and company
    res = client.post(
        "/api/staging/bulk-allocate",
        json={
            "staged_transaction_ids": [str(st.id)],
            "is_personal": True,
            "company_id": str(uuid.uuid4()),
        },
        headers=auth_headers,
    )
    assert res.status_code == 422

    # 3. Clear with personal/company
    res = client.post(
        "/api/staging/bulk-allocate",
        json={
            "staged_transaction_ids": [str(st.id)],
            "clear": True,
            "is_personal": True,
        },
        headers=auth_headers,
    )
    assert res.status_code == 422

    # 4. Omitting all entity fields (is_personal=False, company_id=None, clear=False)
    res = client.post(
        "/api/staging/bulk-allocate",
        json={"staged_transaction_ids": [str(st.id)]},
        headers=auth_headers,
    )
    assert res.status_code == 422

    # 5. Non-existent company ID
    res = client.post(
        "/api/staging/bulk-allocate",
        json={"staged_transaction_ids": [str(st.id)], "company_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "Company not found" in res.json()["detail"]

    # 6. Transaction with missing total_amount
    res = client.post(
        "/api/staging/bulk-allocate",
        json={"staged_transaction_ids": [str(st_no_amount.id)], "is_personal": True},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "Cannot allocate staged transaction without a total amount" in res.json()["detail"]


def test_bulk_dismiss(client, auth_headers, db_session, markable_importer, tmp_path):
    # Setup dummy receipt file
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    file_path = receipt_dir / "dummy_bulk.pdf"
    file_path.write_text("dummy receipt content")

    c1 = Company(id=uuid.uuid4(), name="Company A")
    db_session.add(c1)
    st1 = StagedTransaction(
        id=uuid.uuid4(),
        source="markable_source",
        external_id="DISM-1",
        date=date(2026, 4, 9),
        description="Dismissable 1",
        total_amount=Decimal("15.00"),
        receipt_file_path=str(file_path),
        status="STAGED",
    )
    st2 = StagedTransaction(
        id=uuid.uuid4(),
        source="markable_source",
        external_id="DISM-2",
        date=date(2026, 4, 10),
        description="Dismissable 2",
        total_amount=Decimal("25.00"),
        status="STAGED",
    )
    db_session.add_all([st1, st2])
    db_session.flush()
    db_session.add(StagedAllocation(staged_transaction_id=st1.id, amount=Decimal("15.00"), is_personal=True))
    db_session.add(StagedAllocation(staged_transaction_id=st2.id, amount=Decimal("25.00"), is_personal=False, company_id=c1.id))
    db_session.commit()

    # Empty list error
    res_empty = client.post(
        "/api/staging/bulk-dismiss",
        json={"staged_transaction_ids": []},
        headers=auth_headers,
    )
    assert res_empty.status_code == 400

    # Successful bulk dismiss
    res = client.post(
        "/api/staging/bulk-dismiss",
        json={"staged_transaction_ids": [str(st1.id), str(st2.id)]},
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["dismissed_count"] == 2
    assert set(body["staged_transaction_ids"]) == {str(st1.id), str(st2.id)}
    assert body["marked_imported_count"] == 2
    assert body["mark_imported_errors"] == []
    assert markable_importer.marked_batches == [["DISM-1", "DISM-2"]]

    # Verify disk receipt cleanup and DB state
    assert not file_path.exists()
    db_session.expire_all()
    for st_id in [st1.id, st2.id]:
        refreshed = db_session.get(StagedTransaction, st_id)
        assert refreshed.status == "DISMISSED"
        assert refreshed.receipt_file_path is None
        assert len(refreshed.allocations) == 0
        assert refreshed.is_marked_imported is True


def test_bulk_dismiss_handles_importer_error(client, auth_headers, db_session, markable_importer):
    markable_importer.should_fail = True
    st = StagedTransaction(
        id=uuid.uuid4(),
        source="markable_source",
        external_id="FAIL-1",
        date=date(2026, 4, 11),
        description="Importer Will Fail",
        total_amount=Decimal("40.00"),
        status="STAGED",
    )
    db_session.add(st)
    db_session.commit()

    res = client.post(
        "/api/staging/bulk-dismiss",
        json={"staged_transaction_ids": [str(st.id)]},
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["dismissed_count"] == 1
    assert body["marked_imported_count"] == 0
    assert len(body["mark_imported_errors"]) == 1
    assert "External API timeout" in body["mark_imported_errors"][0]

    db_session.expire_all()
    refreshed = db_session.get(StagedTransaction, st.id)
    assert refreshed.status == "DISMISSED"
    assert refreshed.is_marked_imported is False
