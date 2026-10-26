import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from alembic import command
from models.checklist import ChecklistConfig, MonthlyChecklist
from models.company import Company


def test_checklist_config_defaults_and_relationship(db_session):
    config = ChecklistConfig()
    db_session.add(config)
    db_session.commit()
    db_session.refresh(config)

    assert config.id == 1
    assert config.company_id is None
    assert config.chequing_wave_account_id is None
    assert config.chequing_wave_account_name is None
    assert config.mastercard_wave_account_id is None
    assert config.mastercard_wave_account_name is None
    assert config.tax_expense_wave_account_id is None
    assert config.tax_expense_wave_account_name is None
    assert config.tax_payable_wave_account_id is None
    assert config.tax_payable_wave_account_name is None
    assert config.wave_web_business_slug == "d2977f10-6793-4504-a139-f0d6872b2628"
    assert config.last_chequing_tx_date is None
    assert config.last_mastercard_tx_date is None
    assert config.company is None

    # Test company relationship and foreign key SET NULL behavior
    company = Company(name="Checklist Test LTD")
    db_session.add(company)
    db_session.commit()

    config.company_id = company.id
    config.last_chequing_tx_date = datetime.date(2026, 9, 28)
    config.last_mastercard_tx_date = datetime.date(2026, 9, 24)
    db_session.commit()
    db_session.refresh(config)

    assert config.company is not None
    assert config.company.name == "Checklist Test LTD"
    assert config.last_chequing_tx_date == datetime.date(2026, 9, 28)
    assert config.last_mastercard_tx_date == datetime.date(2026, 9, 24)


def test_monthly_checklist_defaults_and_properties(db_session):
    checklist = MonthlyChecklist(year_month="2026-09")
    db_session.add(checklist)
    db_session.commit()
    db_session.refresh(checklist)

    assert checklist.year_month == "2026-09"
    assert checklist.completed_steps == []
    assert checklist.tax_rate == Decimal("12.00")
    assert checklist.prior_soft_cap == Decimal("17600.00")
    assert checklist.monthly_loc_reduction == Decimal("400.00")
    assert checklist.current_soft_cap == Decimal("17200.00")
    assert checklist.tax_reserve_amount is None
    assert checklist.maximum_safe_draw is None

    # Test completed_steps getter and setter
    checklist.completed_steps = ["import_chequing", "import_mastercard"]
    assert checklist.completed_steps_json == '["import_chequing", "import_mastercard"]'
    assert checklist.completed_steps == ["import_chequing", "import_mastercard"]

    # Test fallback for invalid JSON
    checklist.completed_steps_json = "invalid-json"
    assert checklist.completed_steps == []
    checklist.completed_steps_json = ""
    assert checklist.completed_steps == []

    # Test tax_reserve_amount property
    checklist.net_operating_cash = None
    assert checklist.tax_reserve_amount is None

    checklist.net_operating_cash = Decimal("-500.00")
    assert checklist.tax_reserve_amount == Decimal("0.00")

    checklist.net_operating_cash = Decimal("0.00")
    assert checklist.tax_reserve_amount == Decimal("0.00")

    checklist.net_operating_cash = Decimal("1000.00")
    checklist.tax_rate = Decimal("12.00")
    assert checklist.tax_reserve_amount == Decimal("120.00")

    checklist.net_operating_cash = Decimal("1000.45")
    checklist.tax_rate = Decimal("12.50")
    # 1000.45 * 0.125 = 125.05625 -> 125.06
    assert checklist.tax_reserve_amount == Decimal("125.06")

    # Test current_soft_cap calculation
    checklist.prior_soft_cap = Decimal("17200.00")
    checklist.monthly_loc_reduction = Decimal("400.00")
    assert checklist.current_soft_cap == Decimal("16800.00")

    # Test maximum_safe_draw calculation
    assert checklist.maximum_safe_draw is None

    checklist.tax_liability = Decimal("1800.00")
    assert checklist.maximum_safe_draw is None

    checklist.actual_loc_balance = Decimal("5000.00")
    # 16800.00 - 1800.00 - 5000.00 = 10000.00
    assert checklist.maximum_safe_draw == Decimal("10000.00")


def test_monthly_checklist_unique_year_month(db_session):
    c1 = MonthlyChecklist(year_month="2026-10")
    db_session.add(c1)
    db_session.commit()

    c2 = MonthlyChecklist(year_month="2026-10")
    db_session.add(c2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_alembic_migration_checklist_tables(tmp_path):
    db_file = tmp_path / "test_checklist_migration.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Upgrade to down_revision: d5c8e3f1a2b7
    command.upgrade(alembic_cfg, "d5c8e3f1a2b7")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables_before = inspector.get_table_names()
    assert "checklist_configs" not in tables_before
    assert "monthly_checklists" not in tables_before

    # Upgrade to e1f2a3b4c5d6
    command.upgrade(alembic_cfg, "e1f2a3b4c5d6")
    inspector = inspect(engine)
    tables_after = inspector.get_table_names()
    assert "checklist_configs" in tables_after
    assert "monthly_checklists" in tables_after

    config_cols = {col["name"] for col in inspector.get_columns("checklist_configs")}
    assert "wave_web_business_slug" in config_cols
    assert "last_chequing_tx_date" in config_cols
    assert "last_mastercard_tx_date" in config_cols

    monthly_cols = {col["name"] for col in inspector.get_columns("monthly_checklists")}
    assert "year_month" in monthly_cols
    assert "completed_steps_json" in monthly_cols
    assert "tax_reserve_amount" not in monthly_cols  # computed property, not column
    assert "maximum_safe_draw" not in monthly_cols  # computed property, not column

    monthly_indexes = {idx["name"] for idx in inspector.get_indexes("monthly_checklists")}
    assert "ix_monthly_checklists_year_month" in monthly_indexes

    # Downgrade back to d5c8e3f1a2b7
    command.downgrade(alembic_cfg, "d5c8e3f1a2b7")
    inspector = inspect(engine)
    tables_downgraded = inspector.get_table_names()
    assert "checklist_configs" not in tables_downgraded
    assert "monthly_checklists" not in tables_downgraded
