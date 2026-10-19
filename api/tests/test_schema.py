import datetime
import uuid
from decimal import Decimal

from sqlalchemy import create_engine, inspect

from database import Base
from models.allocation import Allocation  # noqa: F401
from models.company import Company  # noqa: F401
from models.staged_allocation import StagedAllocation  # noqa: F401
from models.staged_transaction import StagedTransaction  # noqa: F401
from models.transaction import Transaction  # noqa: F401
from schemas.staging import StagedTransactionResponse
from schemas.transaction import TransactionCreate, TransactionResponse


def test_database_schema_setup():
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    inspector = inspect(test_engine)

    # 1. Verify tables
    tables = inspector.get_table_names()
    assert "companies" in tables
    assert "wave_categories" not in tables
    assert "transactions" in tables
    assert "allocations" in tables
    assert "staged_transactions" in tables
    assert "staged_allocations" in tables

    # 2. Verify columns in companies
    company_cols = {col["name"]: col for col in inspector.get_columns("companies")}
    assert "id" in company_cols
    assert "name" in company_cols
    assert not company_cols["name"]["nullable"]
    assert "wave_equity_account_id" not in company_cols
    assert "wave_business_id" not in company_cols
    assert "wave_access_token" not in company_cols
    assert "wave_refresh_token" not in company_cols
    assert "wave_token_expires_at" not in company_cols

    # 3. Verify columns in transactions
    tx_cols = {col["name"]: col for col in inspector.get_columns("transactions")}
    assert "id" in tx_cols
    assert "source" in tx_cols
    assert "external_id" in tx_cols
    assert "date" in tx_cols
    assert "description" in tx_cols
    assert "total_amount" in tx_cols
    assert "currency_code" not in tx_cols
    assert "receipt_file_path" in tx_cols
    assert "is_approved" not in tx_cols

    staged_tx_cols = {col["name"]: col for col in inspector.get_columns("staged_transactions")}
    assert "currency_code" not in staged_tx_cols

    # 4. Verify columns in allocations
    alloc_cols = {col["name"]: col for col in inspector.get_columns("allocations")}
    assert "id" in alloc_cols
    assert "transaction_id" in alloc_cols
    assert "amount" in alloc_cols
    assert "is_personal" in alloc_cols
    assert "company_id" in alloc_cols
    assert "is_locked" in alloc_cols
    assert "sync_status" not in alloc_cols
    assert "wave_category_id" not in alloc_cols
    assert "wave_transaction_id" not in alloc_cols

    # 5. Verify unique constraints
    tx_unique = inspector.get_unique_constraints("transactions")
    tx_unique_cols = [u["column_names"] for u in tx_unique]
    assert ["source", "external_id"] in tx_unique_cols

    staged_tx_unique = inspector.get_unique_constraints("staged_transactions")
    staged_tx_unique_cols = [u["column_names"] for u in staged_tx_unique]
    assert ["source", "external_id"] in staged_tx_unique_cols

    company_unique = inspector.get_unique_constraints("companies")
    company_unique_cols = [u["column_names"] for u in company_unique]
    assert ["name"] in company_unique_cols

    # 6. Verify foreign keys
    alloc_fks = inspector.get_foreign_keys("allocations")
    referred_tables = {fk["referred_table"] for fk in alloc_fks}
    assert "transactions" in referred_tables
    assert "companies" in referred_tables
    assert "wave_categories" not in referred_tables

    staged_alloc_fks = inspector.get_foreign_keys("staged_allocations")
    staged_referred_tables = {fk["referred_table"] for fk in staged_alloc_fks}
    assert "staged_transactions" in staged_referred_tables
    assert "companies" in staged_referred_tables


def test_pydantic_schemas_without_currency_code():
    # 1. TransactionCreate validation succeeds without currency_code
    tx_create = TransactionCreate(
        date=datetime.date(2026, 10, 18),
        description="Office supplies",
        total_amount=Decimal("45.50"),
        company_id=uuid.uuid4(),
    )
    assert not hasattr(tx_create, "currency_code")
    data = tx_create.model_dump()
    assert "currency_code" not in data

    # 2. TransactionResponse serialization succeeds without currency_code
    tx_resp = TransactionResponse(
        id=uuid.uuid4(),
        source="manual",
        date=datetime.date(2026, 10, 18),
        description="Office supplies",
        total_amount=Decimal("45.50"),
        allocations=[],
    )
    assert not hasattr(tx_resp, "currency_code")
    data_resp = tx_resp.model_dump()
    assert "currency_code" not in data_resp

    # 3. StagedTransactionResponse serialization succeeds without currency_code
    staged_resp = StagedTransactionResponse(
        id=uuid.uuid4(),
        source="manual",
        date=datetime.date(2026, 10, 18),
        description="Staged supplies",
        total_amount=Decimal("45.50"),
        status="STAGED",
        is_marked_imported=False,
        created_at=datetime.datetime.now(datetime.UTC),
        allocations=[],
        is_ready=True,
        supports_mark_imported=False,
    )
    assert not hasattr(staged_resp, "currency_code")
    staged_data = staged_resp.model_dump()
    assert "currency_code" not in staged_data
