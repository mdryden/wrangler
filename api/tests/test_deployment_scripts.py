import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure api root is in sys.path to import scripts
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy.exc import OperationalError

from core.config import settings
from scripts.check_migrations import check_migrations
from scripts.wal_backup import run_backup


def test_check_migrations_up_to_date():
    mock_script = MagicMock()
    mock_script.get_current_head.return_value = "rev_12345"

    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = ("rev_12345",)
    mock_conn.execute.return_value = mock_result

    with (
        patch("scripts.check_migrations.ScriptDirectory.from_config", return_value=mock_script),
        patch("scripts.check_migrations.inspect") as mock_inspect,
        patch("scripts.check_migrations.engine.connect") as mock_connect,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_inspect.return_value.get_table_names.return_value = ["alembic_version", "transactions"]

        code = check_migrations()
        assert code == 0


def test_check_migrations_pending_rev():
    mock_script = MagicMock()
    mock_script.get_current_head.return_value = "rev_head"

    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = ("rev_old",)
    mock_conn.execute.return_value = mock_result

    with (
        patch("scripts.check_migrations.ScriptDirectory.from_config", return_value=mock_script),
        patch("scripts.check_migrations.inspect") as mock_inspect,
        patch("scripts.check_migrations.engine.connect") as mock_connect,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_inspect.return_value.get_table_names.return_value = ["alembic_version"]

        code = check_migrations()
        assert code == 2


def test_check_migrations_missing_version_table():
    mock_script = MagicMock()
    mock_script.get_current_head.return_value = "rev_head"

    mock_conn = MagicMock()

    with (
        patch("scripts.check_migrations.ScriptDirectory.from_config", return_value=mock_script),
        patch("scripts.check_migrations.inspect") as mock_inspect,
        patch("scripts.check_migrations.engine.connect") as mock_connect,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_inspect.return_value.get_table_names.return_value = ["transactions"]

        code = check_migrations()
        assert code == 2


def test_check_migrations_connection_error():
    with patch("scripts.check_migrations.engine.connect", side_effect=OperationalError("mock failure", params=None, orig=Exception())):
        code = check_migrations()
        assert code == 1


def test_wal_backup_noop_when_backup_dir_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BACKUP_DIR", raising=False)
    monkeypatch.setattr(settings, "BACKUP_DIR", None)
    exit_code = run_backup()
    assert exit_code == 0


def test_wal_backup_success_from_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_dir = tmp_path / "backup_dest_settings"
    monkeypatch.delenv("BACKUP_DIR", raising=False)
    monkeypatch.setattr(settings, "BACKUP_DIR", backup_dir)

    exit_code = run_backup()
    assert exit_code == 0
    assert (backup_dir / "wrangler.db").is_file()


def test_wal_backup_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_dir = tmp_path / "backup_dest"
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))

    # Create dummy receipt in settings.RECEIPT_STORAGE_DIR
    dummy_receipt = settings.RECEIPT_STORAGE_DIR / "test_backup_receipt.pdf"
    dummy_receipt.write_text("dummy receipt data", encoding="utf-8")

    try:
        exit_code = run_backup()
        assert exit_code == 0
        assert (backup_dir / "wrangler.db").is_file()
        assert (backup_dir / "receipts" / "test_backup_receipt.pdf").is_file()
        assert not (backup_dir / "wrangler.db.tmp").exists()
    finally:
        if dummy_receipt.exists():
            dummy_receipt.unlink()


def test_wal_backup_error_handling_and_tmp_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_dir = tmp_path / "backup_dest_error"
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))

    with patch("scripts.wal_backup.engine.connect", side_effect=Exception("Database lock error")):
        exit_code = run_backup()
        assert exit_code == 1
        assert not (backup_dir / "wrangler.db.tmp").exists()
        assert not (backup_dir / "wrangler.db").exists()
