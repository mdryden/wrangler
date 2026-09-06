import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from models.company import Company
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
