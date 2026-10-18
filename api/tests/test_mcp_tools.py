import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from models.staged_transaction import StagedTransaction
from models.transaction import Transaction
from services.mcp import check_transaction_exists, stage_transaction


@pytest.fixture
def mock_mcp_session(monkeypatch, db_session):
    testing_session_local = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr("services.mcp.SessionLocal", testing_session_local)
    return db_session


@pytest.mark.anyio
async def test_stage_transaction_success_and_normalization(mock_mcp_session):
    result = await stage_transaction(
        source_label="  aMaZoN  ",
        external_id="  114-1234567-8901234  ",
        date="2026-10-15",
        total_amount=29.99,
        description="  Wireless Keyboard  ",
        currency_code="cad",
    )

    assert "Successfully staged transaction" in result
    assert "[mcp] amazon:114-1234567-8901234" in result
    assert "[Amazon] Wireless Keyboard" in result
    assert "($29.99 CAD)" in result

    staged = (
        mock_mcp_session.query(StagedTransaction)
        .filter(StagedTransaction.source == "mcp", StagedTransaction.external_id == "amazon:114-1234567-8901234")
        .first()
    )
    assert staged is not None
    assert staged.description == "[Amazon] Wireless Keyboard"
    assert staged.total_amount == Decimal("29.99")
    assert staged.currency_code == "CAD"
    assert staged.date == datetime.date(2026, 10, 15)
    assert staged.status == "STAGED"
    assert staged.is_marked_imported is False


@pytest.mark.anyio
async def test_stage_transaction_email_source_label_used_verbatim(mock_mcp_session):
    result = await stage_transaction(
        source_label="Receipts@mmjm.ca",
        external_id="IAd5p4TqJGc-1",
        date="2026-10-17",
        total_amount=42.10,
        description="Amazon: USB-C Hub",
    )
    assert "[mcp] receipts@mmjm.ca:IAd5p4TqJGc-1" in result

    staged = mock_mcp_session.query(StagedTransaction).filter(StagedTransaction.external_id == "receipts@mmjm.ca:IAd5p4TqJGc-1").first()
    assert staged is not None
    assert staged.description == "[receipts@mmjm.ca] Amazon: USB-C Hub"

    # Re-staging with an already-prefixed description does not double the prefix
    again = await stage_transaction(
        source_label="receipts@mmjm.ca",
        external_id="IAd5p4TqJGc-2",
        date="2026-10-17",
        total_amount=5.00,
        description="[receipts@mmjm.ca] Coffee",
    )
    assert "[receipts@mmjm.ca] Coffee" in again
    assert "[receipts@mmjm.ca] [receipts@mmjm.ca]" not in again


@pytest.mark.anyio
async def test_stage_transaction_description_already_prefixed(mock_mcp_session):
    result = await stage_transaction(
        source_label="target",
        external_id="order-999",
        date="2026-10-16",
        total_amount=15.50,
        description="[Target] Desk Lamp",
        currency_code="USD",
    )
    assert "Successfully staged transaction" in result

    staged = mock_mcp_session.query(StagedTransaction).filter(StagedTransaction.source == "mcp", StagedTransaction.external_id == "target:order-999").first()
    assert staged is not None
    assert staged.description == "[Target] Desk Lamp"
    assert staged.currency_code == "USD"


@pytest.mark.anyio
async def test_stage_transaction_validation_errors(mock_mcp_session):
    # Empty source label
    with pytest.raises(ValueError, match="source_label cannot be empty"):
        await stage_transaction(
            source_label="   ",
            external_id="id-1",
            date="2026-10-15",
            total_amount=10.0,
            description="Item",
        )

    # Empty external ID
    with pytest.raises(ValueError, match="external_id cannot be empty"):
        await stage_transaction(
            source_label="amazon",
            external_id="   ",
            date="2026-10-15",
            total_amount=10.0,
            description="Item",
        )

    # Zero total amount
    with pytest.raises(ValueError, match="total_amount cannot be zero"):
        await stage_transaction(
            source_label="amazon",
            external_id="id-1",
            date="2026-10-15",
            total_amount=0.00,
            description="Item",
        )

    # Invalid date
    with pytest.raises(ValueError, match="Invalid date format"):
        await stage_transaction(
            source_label="amazon",
            external_id="id-1",
            date="invalid-date",
            total_amount=10.0,
            description="Item",
        )


@pytest.mark.anyio
async def test_stage_transaction_iso_timestamp_parsing(mock_mcp_session):
    result = await stage_transaction(
        source_label="bestbuy",
        external_id="bb-456",
        date="2026-10-17T18:12:53-05:00",
        total_amount=120.00,
        description="Monitor",
    )
    assert "Successfully staged transaction" in result

    staged = mock_mcp_session.query(StagedTransaction).filter(StagedTransaction.source == "mcp", StagedTransaction.external_id == "bestbuy:bb-456").first()
    assert staged is not None
    assert staged.date == datetime.date(2026, 10, 17)


@pytest.mark.anyio
async def test_stage_transaction_negative_refund_amount(mock_mcp_session):
    result = await stage_transaction(
        source_label="amazon",
        external_id="refund-123",
        date="2026-10-18",
        total_amount=-45.50,
        description="Returned Headphones",
    )
    assert "Successfully staged transaction" in result
    assert "($-45.50 CAD)" in result

    staged = mock_mcp_session.query(StagedTransaction).filter(StagedTransaction.source == "mcp", StagedTransaction.external_id == "amazon:refund-123").first()
    assert staged is not None
    assert staged.total_amount == Decimal("-45.50")


@pytest.mark.anyio
async def test_stage_transaction_deduplication_against_staging(mock_mcp_session):
    # Insert existing staged records in STAGED, ACCEPTED, DISMISSED states
    statuses = ["STAGED", "ACCEPTED", "DISMISSED"]
    for status in statuses:
        ext_id = f"amazon:order-{status.lower()}"
        staged_tx = StagedTransaction(
            id=uuid.uuid4(),
            source="mcp",
            external_id=ext_id,
            date=datetime.date(2026, 10, 10),
            description=f"[Amazon] Order {status}",
            total_amount=Decimal("50.00"),
            currency_code="CAD",
            status=status,
            is_marked_imported=False,
        )
        mock_mcp_session.add(staged_tx)
    mock_mcp_session.commit()

    # Re-staging each should yield an idempotent skip response with the right status
    for status in statuses:
        res = await stage_transaction(
            source_label="amazon",
            external_id=f"order-{status.lower()}",
            date="2026-10-10",
            total_amount=50.00,
            description="Order duplicate attempt",
        )
        assert f"Transaction '[mcp] amazon:order-{status.lower()}' already exists in Wrangler (status: {status}). Skipped." == res


@pytest.mark.anyio
async def test_stage_transaction_deduplication_against_ledger(mock_mcp_session):
    # Insert a committed transaction in the ledger
    ledger_tx = Transaction(
        id=uuid.uuid4(),
        source="mcp",
        external_id="amazon:ledger-tx-1",
        date=datetime.date(2026, 9, 20),
        description="[Amazon] Office Chair",
        total_amount=Decimal("199.99"),
        currency_code="CAD",
    )
    mock_mcp_session.add(ledger_tx)
    mock_mcp_session.commit()

    res = await stage_transaction(
        source_label="amazon",
        external_id="ledger-tx-1",
        date="2026-09-20",
        total_amount=199.99,
        description="Office Chair",
    )
    assert res == "Transaction '[mcp] amazon:ledger-tx-1' already exists in Wrangler (status: LEDGER). Skipped."


@pytest.mark.anyio
async def test_check_transaction_exists(mock_mcp_session):
    # 1. Non-existent transaction
    check_none = await check_transaction_exists("amazon", "non-existent-order")
    assert check_none == {"exists": False, "location": None, "status": None}

    # 2. Transaction in Staging (STAGED)
    staged_tx = StagedTransaction(
        id=uuid.uuid4(),
        source="mcp",
        external_id="amazon:staged-check-1",
        date=datetime.date(2026, 10, 1),
        description="[Amazon] Staged Check",
        total_amount=Decimal("25.00"),
        currency_code="CAD",
        status="STAGED",
    )
    mock_mcp_session.add(staged_tx)

    # 3. Transaction in Staging (DISMISSED)
    dismissed_tx = StagedTransaction(
        id=uuid.uuid4(),
        source="mcp",
        external_id="amazon:dismissed-check-1",
        date=datetime.date(2026, 10, 2),
        description="[Amazon] Dismissed Check",
        total_amount=Decimal("10.00"),
        currency_code="CAD",
        status="DISMISSED",
    )
    mock_mcp_session.add(dismissed_tx)

    # 4. Transaction in Ledger
    ledger_tx = Transaction(
        id=uuid.uuid4(),
        source="mcp",
        external_id="amazon:ledger-check-1",
        date=datetime.date(2026, 10, 3),
        description="[Amazon] Ledger Check",
        total_amount=Decimal("80.00"),
        currency_code="CAD",
    )
    mock_mcp_session.add(ledger_tx)
    mock_mcp_session.commit()

    # Check STAGED
    check_staged = await check_transaction_exists("AMAZON", " staged-check-1 ")
    assert check_staged == {"exists": True, "location": "staged", "status": "STAGED"}

    # Check DISMISSED
    check_dismissed = await check_transaction_exists("amazon", "dismissed-check-1")
    assert check_dismissed == {"exists": True, "location": "staged", "status": "DISMISSED"}

    # Check LEDGER
    check_ledger = await check_transaction_exists("amazon", "ledger-check-1")
    assert check_ledger == {"exists": True, "location": "ledger", "status": "COMMITTED"}


@pytest.mark.anyio
async def test_stage_transaction_partial_fields_and_readiness(mock_mcp_session):
    from schemas.staging import compute_staged_is_ready

    # 1. Stage with only source_label and external_id (all optional fields omitted)
    res = await stage_transaction(
        source_label="receipts@mmjm.ca",
        external_id="partial-thread-1",
    )
    assert "Successfully staged transaction" in res
    assert "[mcp] receipts@mmjm.ca:partial-thread-1" in res
    assert "Needs review in Wrangler: date, total_amount, description." in res

    staged = mock_mcp_session.query(StagedTransaction).filter(StagedTransaction.external_id == "receipts@mmjm.ca:partial-thread-1").first()
    assert staged is not None
    assert staged.date is None
    assert staged.total_amount is None
    assert staged.description is None
    assert staged.currency_code == "CAD"
    assert staged.status == "STAGED"
    assert compute_staged_is_ready(staged) is False

    # 2. Re-staging does not overwrite partial data (existing records are never modified)
    res_repeat = await stage_transaction(
        source_label="receipts@mmjm.ca",
        external_id="partial-thread-1",
        date="2026-10-17",
        total_amount=50.00,
        description="USB Hub",
    )
    assert "already exists in Wrangler (status: STAGED). Skipped." in res_repeat
    mock_mcp_session.refresh(staged)
    assert staged.date is None
    assert staged.total_amount is None

    # 3. Stage with partial metadata (e.g. amount and date known, description unknown)
    res_partial_2 = await stage_transaction(
        source_label="amazon",
        external_id="partial-thread-2",
        date="2026-10-17",
        total_amount=24.99,
    )
    assert "Successfully staged transaction" in res_partial_2
    assert "Needs review in Wrangler: description." in res_partial_2

    staged_2 = mock_mcp_session.query(StagedTransaction).filter(StagedTransaction.external_id == "amazon:partial-thread-2").first()
    assert staged_2 is not None
    assert staged_2.date == datetime.date(2026, 10, 17)
    assert staged_2.total_amount == Decimal("24.99")
    assert staged_2.description is None
    assert compute_staged_is_ready(staged_2) is False
