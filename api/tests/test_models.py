import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from models.allocation import Allocation, SyncStatus
from models.company import Company
from models.transaction import Transaction
from models.wave_category import WaveCategory


def test_company_creation_defaults(db_session):
    company = Company(name="Acme Corp", wave_equity_account_id="equity-123")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    assert isinstance(company.id, uuid.UUID)
    assert company.name == "Acme Corp"
    assert company.wave_equity_account_id == "equity-123"
    assert company.wave_business_id is None
    assert company.wave_access_token is None
    assert company.wave_refresh_token is None
    assert company.wave_token_expires_at is None


def test_company_creation_with_all_fields(db_session):
    custom_id = uuid.uuid4()
    expires_at = datetime(2026, 12, 31, 23, 59, 59)
    company = Company(
        id=custom_id,
        name="Globex Inc",
        wave_business_id="biz_987",
        wave_access_token="access_token_123",
        wave_refresh_token="refresh_token_456",
        wave_token_expires_at=expires_at,
        wave_equity_account_id="equity_789",
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    assert company.id == custom_id
    assert company.name == "Globex Inc"
    assert company.wave_business_id == "biz_987"
    assert company.wave_access_token == "access_token_123"
    assert company.wave_refresh_token == "refresh_token_456"
    assert company.wave_token_expires_at == expires_at
    assert company.wave_equity_account_id == "equity_789"


def test_company_missing_required_fields(db_session):
    company = Company(name=None, wave_equity_account_id="equity-123")
    db_session.add(company)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_wave_category_creation_defaults(db_session):
    company = Company(name="Acme Corp", wave_equity_account_id="equity-123")
    db_session.add(company)
    db_session.commit()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_wave_123",
        name="Office Supplies",
    )
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)

    assert isinstance(category.id, uuid.UUID)
    assert category.company_id == company.id
    assert category.wave_account_id == "acc_wave_123"
    assert category.name == "Office Supplies"
    assert category.company.id == company.id


def test_wave_category_creation_with_explicit_id(db_session):
    company = Company(name="Acme Corp", wave_equity_account_id="equity-123")
    db_session.add(company)
    db_session.commit()

    custom_id = uuid.uuid4()
    category = WaveCategory(
        id=custom_id,
        company_id=company.id,
        wave_account_id="acc_wave_456",
        name="Advertising",
    )
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)

    assert category.id == custom_id
    assert category.name == "Advertising"


def test_wave_category_missing_required_fields(db_session):
    company = Company(name="Acme Corp", wave_equity_account_id="equity-123")
    db_session.add(company)
    db_session.commit()

    # Missing name
    category = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_wave_123",
        name=None,
    )
    db_session.add(category)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Missing wave_account_id
    category = WaveCategory(
        company_id=company.id,
        wave_account_id=None,
        name="Office Supplies",
    )
    db_session.add(category)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Missing company_id
    category = WaveCategory(
        company_id=None,
        wave_account_id="acc_wave_123",
        name="Office Supplies",
    )
    db_session.add(category)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_wave_category_foreign_key_constraint(db_session):
    non_existent_company_id = uuid.uuid4()
    category = WaveCategory(
        company_id=non_existent_company_id,
        wave_account_id="acc_wave_123",
        name="Office Supplies",
    )
    db_session.add(category)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_wave_category_unique_constraint(db_session):
    company = Company(name="Acme Corp", wave_equity_account_id="equity-123")
    db_session.add(company)
    db_session.commit()

    cat1 = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_dup_123",
        name="Office Supplies",
    )
    db_session.add(cat1)
    db_session.commit()

    cat2 = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_dup_123",
        name="Duplicate Account",
    )
    db_session.add(cat2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_wave_category_cascade_delete(db_session):
    company = Company(name="Acme Corp", wave_equity_account_id="equity-123")
    db_session.add(company)
    db_session.commit()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_cascade_123",
        name="Travel Expenses",
    )
    db_session.add(category)
    db_session.commit()

    cat_id = category.id
    db_session.delete(company)
    db_session.commit()

    deleted_cat = db_session.get(WaveCategory, cat_id)
    assert deleted_cat is None


def test_transaction_creation_defaults(db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Office chairs",
        total_amount=Decimal("150.00"),
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)

    assert isinstance(tx.id, uuid.UUID)
    assert tx.source == "manual"
    assert tx.external_id is None
    assert tx.date == date(2026, 9, 6)
    assert tx.description == "Office chairs"
    assert tx.total_amount == Decimal("150.00")
    assert tx.currency_code == "USD"
    assert tx.receipt_file_path is None
    assert tx.is_approved is False
    assert tx.allocations == []


def test_transaction_creation_with_all_fields(db_session):
    custom_id = uuid.uuid4()
    tx = Transaction(
        id=custom_id,
        source="amazon",
        external_id="111-2223334-5555555",
        date=date(2026, 8, 15),
        description="Refund for returned item",
        total_amount=Decimal("-45.99"),
        currency_code="CAD",
        receipt_file_path="receipts/2026/08/order-111.pdf",
        is_approved=True,
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)

    assert tx.id == custom_id
    assert tx.source == "amazon"
    assert tx.external_id == "111-2223334-5555555"
    assert tx.date == date(2026, 8, 15)
    assert tx.description == "Refund for returned item"
    assert tx.total_amount == Decimal("-45.99")
    assert tx.currency_code == "CAD"
    assert tx.receipt_file_path == "receipts/2026/08/order-111.pdf"
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
        source="amazon",
        external_id="dup-order-1",
        date=date(2026, 9, 1),
        description="Item 1",
        total_amount=Decimal("20.00"),
    )
    db_session.add(tx1)
    db_session.commit()

    tx2 = Transaction(
        source="amazon",
        external_id="dup-order-1",
        date=date(2026, 9, 2),
        description="Item 2 duplicate",
        total_amount=Decimal("25.00"),
    )
    db_session.add(tx2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Multiple transactions with NULL external_id from same source are allowed
    tx_null1 = Transaction(
        source="manual",
        external_id=None,
        date=date(2026, 9, 1),
        description="Cash 1",
        total_amount=Decimal("10.00"),
    )
    tx_null2 = Transaction(
        source="manual",
        external_id=None,
        date=date(2026, 9, 2),
        description="Cash 2",
        total_amount=Decimal("20.00"),
    )
    db_session.add_all([tx_null1, tx_null2])
    db_session.commit()
    assert tx_null1.id is not None
    assert tx_null2.id is not None


def test_allocation_creation_defaults(db_session):
    tx = Transaction(
        source="manual",
        date=date(2026, 9, 6),
        description="Dinner",
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
    assert alloc.wave_category_id is None
    assert alloc.sync_status == SyncStatus.PENDING
    assert alloc.wave_transaction_id is None
    assert alloc.transaction == tx
    assert alloc in tx.allocations


def test_allocation_creation_with_all_fields(db_session):
    company = Company(name="Acme Corp", wave_equity_account_id="equity-123")
    db_session.add(company)
    db_session.commit()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_123",
        name="Travel",
    )
    db_session.add(category)

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
        wave_category_id=category.id,
        sync_status=SyncStatus.SYNCED,
        wave_transaction_id="wave_tx_999",
    )
    db_session.add(alloc)
    db_session.commit()
    db_session.refresh(alloc)

    assert alloc.id == custom_id
    assert alloc.transaction_id == tx.id
    assert alloc.amount == Decimal("500.00")
    assert alloc.is_personal is False
    assert alloc.company_id == company.id
    assert alloc.wave_category_id == category.id
    assert alloc.sync_status == SyncStatus.SYNCED
    assert alloc.wave_transaction_id == "wave_tx_999"
    assert alloc.company == company
    assert alloc.wave_category == category


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
        total_amount=Decimal("40.00"),
    )
    db_session.add(tx)
    db_session.commit()

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


def test_allocation_company_category_set_null_on_delete(db_session):
    company = Company(name="Acme Corp", wave_equity_account_id="equity-123")
    db_session.add(company)
    db_session.commit()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="acc_123",
        name="Supplies",
    )
    db_session.add(category)
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
        wave_category_id=category.id,
    )
    db_session.add(alloc)
    db_session.commit()

    # Delete company
    db_session.delete(company)
    db_session.commit()
    db_session.refresh(alloc)

    assert alloc.company_id is None
    # Category was cascade deleted because its parent company was deleted
    assert alloc.wave_category_id is None
