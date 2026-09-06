from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

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
    assert "alembic_version" in tables

    # Downgrade to base
    command.downgrade(alembic_cfg, "base")
    inspector = inspect(engine)
    tables_after_downgrade = inspector.get_table_names()
    assert "companies" not in tables_after_downgrade
    assert "wave_categories" not in tables_after_downgrade
    assert "transactions" not in tables_after_downgrade
    assert "allocations" not in tables_after_downgrade
