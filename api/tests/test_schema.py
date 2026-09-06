from sqlalchemy import inspect

from database import Base, engine
from models.allocation import Allocation  # noqa: F401
from models.company import Company  # noqa: F401
from models.transaction import Transaction  # noqa: F401
from models.wave_category import WaveCategory  # noqa: F401


def test_database_schema_setup():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)

    # 1. Verify tables
    tables = inspector.get_table_names()
    assert "companies" in tables
    assert "wave_categories" in tables
    assert "transactions" in tables
    assert "allocations" in tables

    # 2. Verify columns in companies
    company_cols = {col["name"]: col for col in inspector.get_columns("companies")}
    assert "id" in company_cols
    assert "name" in company_cols
    assert "wave_equity_account_id" in company_cols
    assert not company_cols["name"]["nullable"]
    assert not company_cols["wave_equity_account_id"]["nullable"]

    # 3. Verify columns in wave_categories
    wave_cat_cols = {col["name"]: col for col in inspector.get_columns("wave_categories")}
    assert "id" in wave_cat_cols
    assert "company_id" in wave_cat_cols
    assert "wave_account_id" in wave_cat_cols
    assert "name" in wave_cat_cols

    # 4. Verify columns in transactions
    tx_cols = {col["name"]: col for col in inspector.get_columns("transactions")}
    assert "id" in tx_cols
    assert "source" in tx_cols
    assert "external_id" in tx_cols
    assert "date" in tx_cols
    assert "description" in tx_cols
    assert "total_amount" in tx_cols
    assert "currency_code" in tx_cols
    assert "receipt_file_path" in tx_cols
    assert "is_approved" in tx_cols

    # 5. Verify columns in allocations
    alloc_cols = {col["name"]: col for col in inspector.get_columns("allocations")}
    assert "id" in alloc_cols
    assert "transaction_id" in alloc_cols
    assert "amount" in alloc_cols
    assert "is_personal" in alloc_cols
    assert "company_id" in alloc_cols
    assert "wave_category_id" in alloc_cols
    assert "sync_status" in alloc_cols
    assert "wave_transaction_id" in alloc_cols

    # 6. Verify unique constraints
    tx_unique = inspector.get_unique_constraints("transactions")
    tx_unique_cols = [u["column_names"] for u in tx_unique]
    assert ["source", "external_id"] in tx_unique_cols

    wave_cat_unique = inspector.get_unique_constraints("wave_categories")
    wave_cat_unique_cols = [u["column_names"] for u in wave_cat_unique]
    assert ["company_id", "wave_account_id"] in wave_cat_unique_cols

    # 7. Verify foreign keys
    alloc_fks = inspector.get_foreign_keys("allocations")
    referred_tables = {fk["referred_table"] for fk in alloc_fks}
    assert "transactions" in referred_tables
    assert "companies" in referred_tables
    assert "wave_categories" in referred_tables

    wave_cat_fks = inspector.get_foreign_keys("wave_categories")
    wave_cat_referred = {fk["referred_table"] for fk in wave_cat_fks}
    assert "companies" in wave_cat_referred
