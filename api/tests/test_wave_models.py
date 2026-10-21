import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.allocation import Allocation
from models.company import Company
from models.transaction import Transaction
from models.wave_category import WaveCategory


def test_company_persistence_with_wave_fields(db_session):
    company = Company(
        name="Wave Corp",
        wave_api_token="test-token-123",
        wave_business_id="QnVzaW5lc3M6MTIz",
        wave_business_name="Wave Corp Inc",
        wave_anchor_account_id="QWNjb3VudDoxMjM=",
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    assert company.wave_api_token == "test-token-123"
    assert company.wave_business_id == "QnVzaW5lc3M6MTIz"
    assert company.wave_business_name == "Wave Corp Inc"
    assert company.wave_anchor_account_id == "QWNjb3VudDoxMjM="


def test_wave_category_persistence_and_fk(db_session):
    company = Company(name="Category Corp")
    db_session.add(company)
    db_session.commit()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="QWNjb3VudDox",
        name="Office Supplies",
        account_type="EXPENSE",
        account_subtype=None,
        is_uncategorized=False,
    )
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)

    assert isinstance(category.id, uuid.UUID)
    assert category.company_id == company.id
    assert category.wave_account_id == "QWNjb3VudDox"
    assert category.name == "Office Supplies"
    assert category.account_type == "EXPENSE"
    assert category.is_uncategorized is False
    assert category.company.id == company.id


def test_wave_category_cascade_delete_with_company(db_session):
    company = Company(name="Cascade Corp")
    db_session.add(company)
    db_session.commit()

    cat1 = WaveCategory(
        company_id=company.id,
        wave_account_id="QWNjb3VudDox",
        name="Cat 1",
        account_type="EXPENSE",
    )
    cat2 = WaveCategory(
        company_id=company.id,
        wave_account_id="QWNjb3VudDI=",
        name="Cat 2",
        account_type="EXPENSE",
    )
    db_session.add_all([cat1, cat2])
    db_session.commit()

    assert len(company.categories) == 2

    # Delete company
    db_session.delete(company)
    db_session.commit()

    remaining_cats = db_session.execute(select(WaveCategory).where(WaveCategory.company_id == company.id)).scalars().all()
    assert len(remaining_cats) == 0


def test_wave_category_unique_constraint(db_session):
    company = Company(name="Unique Category Corp")
    db_session.add(company)
    db_session.commit()

    cat1 = WaveCategory(
        company_id=company.id,
        wave_account_id="DUPLICATE_ID",
        name="Supplies",
        account_type="EXPENSE",
    )
    db_session.add(cat1)
    db_session.commit()

    cat2 = WaveCategory(
        company_id=company.id,
        wave_account_id="DUPLICATE_ID",
        name="Other Supplies",
        account_type="EXPENSE",
    )
    db_session.add(cat2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_allocation_wave_category_and_set_null_on_delete(db_session):
    company = Company(name="Alloc Wave Corp")
    db_session.add(company)
    db_session.commit()

    category = WaveCategory(
        company_id=company.id,
        wave_account_id="QWNjb3VudDoz",
        name="Advertising",
        account_type="EXPENSE",
    )
    db_session.add(category)

    tx = Transaction(
        source="MANUAL",
        date=date(2026, 10, 20),
        description="Online Ads",
        total_amount=Decimal("150.00"),
    )
    db_session.add(tx)
    db_session.commit()

    alloc = Allocation(
        transaction_id=tx.id,
        amount=Decimal("150.00"),
        is_personal=False,
        company_id=company.id,
        wave_category_id=category.id,
        wave_transaction_id="tx_wave_123",
    )
    db_session.add(alloc)
    db_session.commit()
    db_session.refresh(alloc)

    assert alloc.wave_category_id == category.id
    assert alloc.wave_category.name == "Advertising"
    assert alloc.wave_transaction_id == "tx_wave_123"

    # Delete the category, allocation's wave_category_id should be SET NULL
    db_session.delete(category)
    db_session.commit()
    db_session.refresh(alloc)

    assert alloc.wave_category_id is None
    assert alloc.wave_transaction_id == "tx_wave_123"
