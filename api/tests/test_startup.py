from fastapi.testclient import TestClient

from core.config import settings
from main import app


def test_receipt_storage_dir_creation_on_startup(tmp_path, monkeypatch):
    test_receipt_dir = tmp_path / "custom_receipts_folder"
    assert not test_receipt_dir.exists()

    monkeypatch.setattr(settings, "RECEIPT_STORAGE_DIR", test_receipt_dir)

    with TestClient(app):
        # App startup lifespan should have executed
        assert test_receipt_dir.exists()
        assert test_receipt_dir.is_dir()
