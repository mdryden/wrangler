import importlib
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config import Settings, settings
from core.security import create_access_token


def test_data_dir_dynamic_path_resolution(tmp_path: Path):
    data_dir = tmp_path / "custom_data"
    assert not data_dir.exists()

    custom_settings = Settings(DATA_DIR=data_dir)

    assert data_dir.exists()
    expected_db = f"sqlite:///{(data_dir / 'wrangler.db').as_posix()}"
    assert custom_settings.DATABASE_URL == expected_db
    assert custom_settings.RECEIPT_STORAGE_DIR == (data_dir / "receipts").resolve()
    assert (data_dir / "receipts").is_dir()


def test_data_dir_explicit_overrides_preserved(tmp_path: Path):
    data_dir = tmp_path / "custom_data_override"
    custom_receipts = tmp_path / "override_receipts"
    custom_db_url = "sqlite:///custom_db.sqlite"

    custom_settings = Settings(
        DATA_DIR=data_dir,
        DATABASE_URL=custom_db_url,
        RECEIPT_STORAGE_DIR=custom_receipts,
    )

    assert custom_settings.DATABASE_URL == custom_db_url
    assert custom_settings.RECEIPT_STORAGE_DIR == custom_receipts.resolve()
    assert custom_receipts.is_dir()


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
