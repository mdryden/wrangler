import uuid
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_alembic_migrations_upgrade_and_downgrade(tmp_path):
    db_file = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Verify tables created
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "companies" in tables
    assert "wave_categories" in tables
    assert "transactions" in tables
    assert "allocations" in tables
    assert "staged_transactions" in tables
    assert "staged_allocations" in tables
    assert "alembic_version" in tables

    # Verify columns at head
    company_cols = {col["name"] for col in inspector.get_columns("companies")}
    assert "wave_equity_account_id" in company_cols
    assert "wave_business_id" in company_cols

    alloc_cols = {col["name"] for col in inspector.get_columns("allocations")}
    assert "is_locked" in alloc_cols
    assert "sync_status" not in alloc_cols
    assert "wave_category_id" in alloc_cols
    assert "wave_transaction_id" in alloc_cols

    tx_cols = {col["name"] for col in inspector.get_columns("transactions")}
    assert "is_approved" not in tx_cols
    assert "currency_code" not in tx_cols

    staged_tx_cols = {col["name"] for col in inspector.get_columns("staged_transactions")}
    assert "currency_code" not in staged_tx_cols
    assert {
        "id",
        "source",
        "external_id",
        "date",
        "description",
        "total_amount",
        "receipt_file_path",
        "url",
        "status",
        "is_marked_imported",
        "ledger_transaction_id",
        "created_at",
    } <= staged_tx_cols

    staged_tx_columns_dict = {col["name"]: col for col in inspector.get_columns("staged_transactions")}
    assert staged_tx_columns_dict["date"]["nullable"] is True
    assert staged_tx_columns_dict["description"]["nullable"] is True
    assert staged_tx_columns_dict["total_amount"]["nullable"] is True
    assert staged_tx_columns_dict["url"]["nullable"] is True

    staged_tx_indexes = {idx["name"] for idx in inspector.get_indexes("staged_transactions")}
    assert "ix_staged_transactions_source" in staged_tx_indexes
    assert "ix_staged_transactions_status" in staged_tx_indexes

    staged_tx_unique = [u["column_names"] for u in inspector.get_unique_constraints("staged_transactions")]
    assert ["source", "external_id"] in staged_tx_unique

    staged_alloc_cols = {col["name"] for col in inspector.get_columns("staged_allocations")}
    assert {"id", "staged_transaction_id", "amount", "is_personal", "company_id"} <= staged_alloc_cols

    # Downgrade to base
    command.downgrade(alembic_cfg, "base")
    inspector = inspect(engine)
    tables_after_downgrade = inspector.get_table_names()
    assert "companies" not in tables_after_downgrade
    assert "wave_categories" not in tables_after_downgrade
    assert "transactions" not in tables_after_downgrade
    assert "allocations" not in tables_after_downgrade
    assert "staged_transactions" not in tables_after_downgrade
    assert "staged_allocations" not in tables_after_downgrade


def test_alembic_migration_sync_status_to_is_locked_data_preservation(tmp_path):
    db_file = tmp_path / "test_data_migration.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Upgrade to revision before is_locked migration
    command.upgrade(alembic_cfg, "f92a4e1d7b38")

    engine = create_engine(db_url)
    tx_id = uuid.uuid4().hex
    pending_id = uuid.uuid4().hex
    synced_id = uuid.uuid4().hex

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, source, date, description, total_amount, currency_code) "
                "VALUES (:id, 'manual', '2026-09-01', 'Migration Test', 100.00, 'USD')"
            ),
            {"id": tx_id},
        )
        conn.execute(
            text("INSERT INTO allocations (id, transaction_id, amount, is_personal, sync_status) VALUES (:id, :tx_id, 40.00, 1, 'PENDING')"),
            {"id": pending_id, "tx_id": tx_id},
        )
        conn.execute(
            text("INSERT INTO allocations (id, transaction_id, amount, is_personal, sync_status) VALUES (:id, :tx_id, 60.00, 1, 'SYNCED')"),
            {"id": synced_id, "tx_id": tx_id},
        )

    # Upgrade to head (a3c8d9e21f04)
    command.upgrade(alembic_cfg, "head")

    with engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT id, is_locked FROM allocations")).fetchall())
        assert bool(rows[pending_id]) is False
        assert bool(rows[synced_id]) is True


def test_alembic_migration_remove_currency_code_upgrade_downgrade(tmp_path):
    db_file = tmp_path / "test_currency_migration.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Upgrade to revision before currency_code drop: e8a1f2c3b4d5
    command.upgrade(alembic_cfg, "e8a1f2c3b4d5")

    engine = create_engine(db_url)
    inspector = inspect(engine)
    tx_cols_before = {col["name"] for col in inspector.get_columns("transactions")}
    staged_tx_cols_before = {col["name"] for col in inspector.get_columns("staged_transactions")}
    assert "currency_code" in tx_cols_before
    assert "currency_code" in staged_tx_cols_before

    # Insert sample rows before migration
    tx_id = uuid.uuid4().hex
    staged_id = uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transactions (id, source, date, description, total_amount, currency_code) "
                "VALUES (:id, 'manual', '2026-09-01', 'Before Migration', 50.00, 'USD')"
            ),
            {"id": tx_id},
        )
        conn.execute(
            text(
                "INSERT INTO staged_transactions "
                "(id, source, external_id, date, description, total_amount, currency_code, status, is_marked_imported, created_at) "
                "VALUES (:id, 'manual', 'ext-1', '2026-09-01', 'Staged Before Migration', 50.00, 'USD', 'PENDING', 0, '2026-09-01 10:00:00')"
            ),
            {"id": staged_id},
        )

    # Upgrade to head (d4a8e2b1c3f5)
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(engine)
    tx_cols_head = {col["name"] for col in inspector.get_columns("transactions")}
    staged_tx_cols_head = {col["name"] for col in inspector.get_columns("staged_transactions")}
    assert "currency_code" not in tx_cols_head
    assert "currency_code" not in staged_tx_cols_head

    # Downgrade back to e8a1f2c3b4d5
    command.downgrade(alembic_cfg, "e8a1f2c3b4d5")

    inspector = inspect(engine)
    tx_cols_downgrade = {col["name"] for col in inspector.get_columns("transactions")}
    staged_tx_cols_downgrade = {col["name"] for col in inspector.get_columns("staged_transactions")}
    assert "currency_code" in tx_cols_downgrade
    assert "currency_code" in staged_tx_cols_downgrade

    # Verify restored default value is 'CAD'
    with engine.connect() as conn:
        tx_row = conn.execute(text("SELECT currency_code FROM transactions WHERE id = :id"), {"id": tx_id}).fetchone()
        assert tx_row[0] == "CAD"
        staged_row = conn.execute(text("SELECT currency_code FROM staged_transactions WHERE id = :id"), {"id": staged_id}).fetchone()
        assert staged_row[0] == "CAD"
