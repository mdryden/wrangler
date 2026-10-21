import importlib
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config import Settings, settings
from core.security import create_access_token


def test_receipt_storage_path_resolution_default_dev():
    custom_settings = Settings(BACKUP_DIR=None)
    assert custom_settings.RECEIPT_STORAGE_DIR == Path("receipts").resolve()
    assert custom_settings.RECEIPT_STORAGE_DIR.is_dir()
    assert custom_settings.BACKUP_SCHEDULE_TIME == "02:00"
    assert custom_settings.DATABASE_URL == "sqlite:///./wrangler.db"


def test_receipt_storage_path_resolution_production(tmp_path: Path):
    custom_backup_path = tmp_path / "backup_dest"
    custom_settings = Settings(BACKUP_DIR=custom_backup_path)

    expected_receipts = (custom_backup_path / "receipts").resolve()
    assert custom_settings.RECEIPT_STORAGE_DIR == expected_receipts
    assert expected_receipts.is_dir()


def test_receipt_storage_path_explicit_override(tmp_path: Path):
    custom_backup_path = tmp_path / "backup_dest"
    custom_receipt_path = tmp_path / "custom_receipts"

    custom_settings = Settings(
        BACKUP_DIR=custom_backup_path,
        RECEIPT_STORAGE_DIR=custom_receipt_path,
    )

    assert custom_settings.RECEIPT_STORAGE_DIR == custom_receipt_path.resolve()
    assert custom_receipt_path.is_dir()


def test_backup_schedule_time_custom():
    custom_settings = Settings(BACKUP_SCHEDULE_TIME="03:45")
    assert custom_settings.BACKUP_SCHEDULE_TIME == "03:45"


def test_unified_spa_serving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Setup temporary directory mimicking web/dist
    fake_dist = tmp_path / "dist"
    fake_assets = fake_dist / "assets"
    fake_assets.mkdir(parents=True, exist_ok=True)

    index_content = "<!DOCTYPE html><html><body><h1>Wrangler SPA</h1></body></html>"
    bundle_content = "console.log('bundle loaded');"
    favicon_content = "fake-favicon-binary-or-text"

    (fake_dist / "index.html").write_text(index_content, encoding="utf-8")
    (fake_assets / "bundle.js").write_text(bundle_content, encoding="utf-8")
    (fake_dist / "favicon.ico").write_text(favicon_content, encoding="utf-8")

    monkeypatch.setattr(settings, "STATIC_DIR", fake_dist)

    # Reload main module so that static routes and asset mounts bind to fake_dist
    import main

    importlib.reload(main)

    token = create_access_token(
        data={"sub": settings.ADMIN_USERNAME},
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
        expires_delta=timedelta(minutes=60),
    )
    auth_headers = {"Authorization": f"Bearer {token}"}
    mcp_headers = {"Authorization": f"Bearer {settings.MCP_API_KEY}"} if settings.MCP_API_KEY else {}

    try:
        with TestClient(main.app) as client:
            # 1. Root path GET / returns 200 with index.html
            res_root = client.get("/")
            assert res_root.status_code == 200
            assert "Wrangler SPA" in res_root.text

            # 2. Client-side route paths return 200 with index.html
            res_ledger = client.get("/ledger")
            assert res_ledger.status_code == 200
            assert "Wrangler SPA" in res_ledger.text

            res_export = client.get("/export-manager")
            assert res_export.status_code == 200
            assert "Wrangler SPA" in res_export.text

            # 3. Asset path GET /assets/bundle.js returns 200 with asset content
            res_bundle = client.get("/assets/bundle.js")
            assert res_bundle.status_code == 200
            assert res_bundle.text == bundle_content

            # 4. Literal root asset GET /favicon.ico returns 200
            res_fav = client.get("/favicon.ico")
            assert res_fav.status_code == 200
            assert res_fav.text == favicon_content

            # 5. Missing API path GET /api/nonexistent returns 404 JSON (not HTML)
            res_api_missing = client.get("/api/nonexistent", headers=auth_headers)
            assert res_api_missing.status_code == 404
            assert res_api_missing.headers["content-type"].startswith("application/json")
            assert res_api_missing.json()["detail"] == "Endpoint not found"

            # 6. Missing MCP path GET /mcp/nonexistent returns 404 (not HTML)
            # Note: /mcp mount catches /mcp/*, or catch-all catches /mcp/nonexistent
            res_mcp_missing = client.get("/mcp/nonexistent", headers=mcp_headers)
            assert res_mcp_missing.status_code == 404
            assert "text/html" not in res_mcp_missing.headers.get("content-type", "")
    finally:
        # Restore original settings and reload main back to repository state
        monkeypatch.undo()
        importlib.reload(main)
