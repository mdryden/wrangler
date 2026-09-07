import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.allocation import Allocation, SyncStatus
from models.company import Company
from models.transaction import Transaction


def test_company_creation_defaults(db_session):
    company = Company(name="Acme Corp")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    assert isinstance(company.id, uuid.UUID)
    assert company.name == "Acme Corp"


def test_company_creation_with_explicit_id(db_session):
    custom_id = uuid.uuid4()
    company = Company(
        id=custom_id,
        name="Globex Inc",
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    assert company.id == custom_id
    assert company.name == "Globex Inc"


def test_company_missing_required_fields(db_session):
    company = Company(name=None)
    db_session.add(company)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_company_unique_name_constraint(db_session):
    company1 = Company(name="Unique Corp")
    db_session.add(company1)
    db_session.commit()

    company2 = Company(name="Unique Corp")
    db_session.add(company2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_transaction_creation_defaults(db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Office lunch",
        total_amount=Decimal("45.50"),
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)

    assert isinstance(tx.id, uuid.UUID)
    assert tx.source == "manual"
    assert tx.external_id is None
    assert tx.date == date(2026, 9, 6)
    assert tx.description == "Office lunch"
    assert tx.total_amount == Decimal("45.50")
    assert tx.currency_code == "USD"
    assert tx.receipt_file_path is None
    assert tx.is_approved is False
    assert tx.allocations == []


def test_transaction_creation_with_all_fields(db_session):
    custom_id = uuid.uuid4()
    tx = Transaction(
        id=custom_id,
        source="amazon",
        external_id="AMZ-ORDER-123",
        date=date(2026, 9, 1),
        description="Monitor stand",
        total_amount=Decimal("-89.99"),  # Test refund / negative amount
        currency_code="CAD",
        receipt_file_path="/receipts/2026/09/amz_123.pdf",
        is_approved=True,
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)

    assert tx.id == custom_id
    assert tx.source == "amazon"
    assert tx.external_id == "AMZ-ORDER-123"
    assert tx.date == date(2026, 9, 1)
    assert tx.description == "Monitor stand"
    assert tx.total_amount == Decimal("-89.99")
    assert tx.currency_code == "CAD"
    assert tx.receipt_file_path == "/receipts/2026/09/amz_123.pdf"
    assert tx.is_approved is True


def test_transaction_missing_required_fields(db_session):
    # Missing source
    tx = Transaction(
        source=None,
        date=date(2026, 9, 6),
        description="Test",
        total_amount=Decimal("10.00"),
    )
    db_session.add(tx)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Missing date
    tx = Transaction(
        source="manual",
        date=None,
        description="Test",
        total_amount=Decimal("10.00"),
    )
    db_session.add(tx)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Missing description
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description=None,
        total_amount=Decimal("10.00"),
    )
    db_session.add(tx)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Missing total_amount
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Test",
        total_amount=None,
    )
    db_session.add(tx)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_transaction_unique_constraint(db_session):
    tx1 = Transaction(
        source="bank_feed",
        external_id="TX_1001",
        date=date(2026, 9, 6),
        description="First instance",
        total_amount=Decimal("25.00"),
    )
    db_session.add(tx1)
    db_session.commit()

    # Same source and external_id must fail
    tx2 = Transaction(
        source="bank_feed",
        external_id="TX_1001",
        date=date(2026, 9, 7),
        description="Duplicate instance",
        total_amount=Decimal("25.00"),
    )
    db_session.add(tx2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Same external_id with different source must succeed
    tx3 = Transaction(
        source="paypal",
        external_id="TX_1001",
        date=date(2026, 9, 6),
        description="Paypal instance",
        total_amount=Decimal("25.00"),
    )
    db_session.add(tx3)
    db_session.commit()

    # Multiple transactions with external_id=None and same source must succeed
    tx4 = Transaction(
        source="manual",
        external_id=None,
        date=date(2026, 9, 6),
        description="Manual 1",
        total_amount=Decimal("10.00"),
    )
    tx5 = Transaction(
        source="manual",
        external_id=None,
        date=date(2026, 9, 6),
        description="Manual 2",
        total_amount=Decimal("20.00"),
    )
    db_session.add_all([tx4, tx5])
    db_session.commit()


def test_allocation_creation_defaults(db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Grocery run",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("100.00"),
    )
    db_session.add(alloc)
    db_session.commit()
    db_session.refresh(alloc)
    db_session.refresh(tx)

    assert isinstance(alloc.id, uuid.UUID)
    assert alloc.transaction_id == tx.id
    assert alloc.amount == Decimal("100.00")
    assert alloc.is_personal is False
    assert alloc.company_id is None
    assert alloc.sync_status == SyncStatus.PENDING
    assert alloc.transaction == tx
    assert alloc in tx.allocations


def test_allocation_creation_with_all_fields(db_session):
    company = Company(name="Acme Corp")
    db_session.add(company)
    db_session.commit()

    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Flight tickets",
        total_amount=Decimal("500.00"),
    )
    db_session.add(tx)
    db_session.commit()

    custom_id = uuid.uuid4()
    alloc = Allocation(
        id=custom_id,
        transaction_id=tx.id,
        amount=Decimal("500.00"),
        is_personal=False,
        company_id=company.id,
        sync_status=SyncStatus.SYNCED,
    )
    db_session.add(alloc)
    db_session.commit()
    db_session.refresh(alloc)

    assert alloc.id == custom_id
    assert alloc.transaction_id == tx.id
    assert alloc.amount == Decimal("500.00")
    assert alloc.is_personal is False
    assert alloc.company_id == company.id
    assert alloc.sync_status == SyncStatus.SYNCED
    assert alloc.company == company


def test_allocation_missing_required_fields(db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Test",
        total_amount=Decimal("10.00"),
    )
    db_session.add(tx)
    db_session.commit()

    # Missing transaction_id
    alloc = Allocation(
        transaction_id=None,
        amount=Decimal("10.00"),
    )
    db_session.add(alloc)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Missing amount
    alloc = Allocation(
        transaction_id=tx.id,
        amount=None,
    )
    db_session.add(alloc)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_allocation_sync_status_enum(db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Test Enum",
        total_amount=Decimal("20.00"),
    )
    db_session.add(tx)
    db_session.commit()

    assert set(SyncStatus) == {SyncStatus.PENDING, SyncStatus.SYNCED}

    for status in SyncStatus:
        alloc = Allocation(
            transaction_id=tx.id,
            amount=Decimal("10.00"),
            sync_status=status,
        )
        db_session.add(alloc)
        db_session.commit()
        db_session.refresh(alloc)
        assert alloc.sync_status == status


def test_allocation_foreign_key_constraint(db_session):
    non_existent_tx_id = uuid.uuid4()
    alloc = Allocation(
        transaction_id=non_existent_tx_id,
        amount=Decimal("10.00"),
    )
    db_session.add(alloc)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_transaction_cascade_delete_allocations(db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Split dinner",
        total_amount=Decimal("100.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc1 = Allocation(transaction_id=tx.id, amount=Decimal("60.00"))
    alloc2 = Allocation(transaction_id=tx.id, amount=Decimal("40.00"))
    db_session.add_all([alloc1, alloc2])
    db_session.commit()

    alloc1_id = alloc1.id
    alloc2_id = alloc2.id

    db_session.delete(tx)
    db_session.commit()

    assert db_session.get(Allocation, alloc1_id) is None
    assert db_session.get(Allocation, alloc2_id) is None


def test_allocation_company_set_null_on_delete(db_session):
    company = Company(name="Acme Corp")
    db_session.add(company)
    db_session.commit()

    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Supplies purchase",
        total_amount=Decimal("50.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("50.00"),
        company_id=company.id,
    )
    db_session.add(alloc)
    db_session.commit()

    # Delete company
    db_session.delete(company)
    db_session.commit()
    db_session.refresh(alloc)

    assert alloc.company_id is None
