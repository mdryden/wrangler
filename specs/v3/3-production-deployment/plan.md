# Implementation Plan: Production Deployment, Release Pipeline & Backup Architecture

This implementation plan defines the deliverables and engineering tasks for establishing the production release pipeline, unified single-process static serving, runtime launcher, smart database migration checks, decoupled data directory architecture, and automated SQLite WAL backup for Wrangler on Windows, as specified in [`specs/v3/3-production-deployment/spec.md`](file:///D:/src/personal/wrangler/specs/v3/3-production-deployment/spec.md).

The plan is organized into sequential phases and atomic implementation tasks. Each task specifies concrete deliverables and automated unit or integration test coverage adhering to project conventions and development standards defined in [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md).

---

## Phase 1: Backend Configuration & Unified SPA Delivery

*Goal:* Enable path-independent and data-isolated execution via centralized `DATA_DIR` and `STATIC_DIR` settings, and configure FastAPI to serve the compiled Vue 3 SPA with full HTML5 history routing.

### 1.1 Extend Backend Settings with `DATA_DIR`, `STATIC_DIR`, and Dynamic Path Resolution
- In [`api/src/core/config.py`](file:///D:/src/personal/wrangler/api/src/core/config.py):
  - Add configuration fields to [`Settings`](file:///D:/src/personal/wrangler/api/src/core/config.py):
    - `DATA_DIR: Path | None = None`
    - `STATIC_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"`
  - Implement a post-init model validator `@model_validator(mode="after")` named `resolve_paths(self) -> "Settings"`:
    - If `self.DATA_DIR is not None`:
      - Resolve path via `resolved_data = self.DATA_DIR.expanduser().resolve()`.
      - Ensure directory exists via `resolved_data.mkdir(parents=True, exist_ok=True)`.
      - If `self.DATABASE_URL == "sqlite:///./wrangler.db"`, automatically set `self.DATABASE_URL = f"sqlite:///{(resolved_data / 'wrangler.db').as_posix()}"`.
      - If `self.RECEIPT_STORAGE_DIR == Path("receipts").resolve()`, automatically set `self.RECEIPT_STORAGE_DIR = (resolved_data / "receipts").resolve()`.
    - Ensure `self.RECEIPT_STORAGE_DIR = Path(self.RECEIPT_STORAGE_DIR).expanduser().resolve()`.
    - Ensure `self.RECEIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)`.
    - Return `self`.
  - Maintain relative import conventions and code formatting standards.

### 1.2 Implement Unified SPA Static Asset Mounting & Catch-All Route
- In [`api/src/main.py`](file:///D:/src/personal/wrangler/api/src/main.py):
  - Import `HTTPException` from `fastapi`, `FileResponse` from `fastapi.responses`, and `StaticFiles` from `fastapi.staticfiles`.
  - At the end of the route registration section (after all `/api/*` and `/mcp/*` routers are registered):
    - Guard on `if settings.STATIC_DIR.is_dir() and (settings.STATIC_DIR / "index.html").is_file():`
    - Mount the compiled static assets directory `/assets` pointing to `settings.STATIC_DIR / "assets"` via `StaticFiles(directory=assets_dir)`.
    - Register the SPA catch-all route `@app.get("/{full_path:path}", include_in_schema=False)`:
      - If `full_path.startswith("api")` or `full_path.startswith("mcp")`, raise `HTTPException(status_code=404, detail="Endpoint not found")` to prevent returning HTML for missing API endpoints.
      - Resolve candidate static files via `candidate_file = (settings.STATIC_DIR / full_path).resolve()`.
      - If `candidate_file.is_file()` and `candidate_file.is_relative_to(settings.STATIC_DIR)`, return `FileResponse(candidate_file)` to support literal root assets (`favicon.ico`, `robots.txt`).
      - Otherwise, return `FileResponse(settings.STATIC_DIR / "index.html")` to allow Vue Router HTML5 history mode navigation.

### 1.3 Automated Test Suite for Configuration & SPA Serving
- Create [`api/tests/test_production_config_and_spa.py`](file:///D:/src/personal/wrangler/api/tests/test_production_config_and_spa.py):
  - Test `DATA_DIR` dynamic path resolution:
    - When `DATA_DIR` is set, verify `resolved_data` directory is created.
    - Verify `DATABASE_URL` defaults to `sqlite:///{DATA_DIR}/wrangler.db`.
    - Verify `RECEIPT_STORAGE_DIR` defaults to `{DATA_DIR}/receipts` and directory is created.
    - Verify explicit `DATABASE_URL` or `RECEIPT_STORAGE_DIR` overrides are preserved.
  - Test unified SPA serving with `TestClient`:
    - Create a temporary directory structure mimicking `web/dist` with `index.html`, `assets/bundle.js`, and `favicon.ico`.
    - Test root path `GET /` returns 200 with `index.html`.
    - Test client-side route paths `GET /ledger` and `GET /export-manager` return 200 with `index.html`.
    - Test asset path `GET /assets/bundle.js` returns 200 with asset content.
    - Test literal root asset `GET /favicon.ico` returns 200.
    - Test missing API path `GET /api/nonexistent` returns 404 JSON (not HTML).
    - Test missing MCP path `GET /mcp/nonexistent` returns 404 JSON (not HTML).

---

## Phase 2: Database Migration & Atomic Backup Automation Helpers

*Goal:* Implement standalone Python helper scripts for deterministic pre-flight migration checking and atomic WAL backups with receipt mirroring.

### 2.1 Implement Migration Pre-Flight Check Script
- Create [`api/scripts/check_migrations.py`](file:///D:/src/personal/wrangler/api/scripts/check_migrations.py):
  - Inspect Alembic head revision against current database revision using `alembic.config.Config`, `alembic.script.ScriptDirectory`, and SQLAlchemy `inspect`.
  - Return exit code 0 when database schema is fully up to date (`current_rev == head_rev`).
  - Return exit code 2 when pending migrations exist or `alembic_version` table is missing.
  - Return exit code 1 on inspection errors or database connection failures.
  - Support execution via `uv run --directory api python scripts/check_migrations.py`.

### 2.2 Implement Atomic SQLite Snapshot & Receipt Mirror Script
- Create [`api/scripts/wal_backup.py`](file:///D:/src/personal/wrangler/api/scripts/wal_backup.py):
  - Read `BACKUP_DIR` from environment. If unset, log notice and return 0 (no-op).
  - Expand and resolve `backup_dir` path, creating target directory if needed.
  - If `DATABASE_URL` is SQLite:
    - Target database: `backup_dir / "wrangler.db"`, staging file: `backup_dir / "wrangler.db.tmp"`.
    - Execute atomic SQLite snapshot via `VACUUM INTO '{staging_file}';`.
    - Atomically replace target database file with temporary staging file.
  - Mirror receipts from `settings.RECEIPT_STORAGE_DIR` to `backup_dir / "receipts"`:
    - On Windows (`sys.platform == "win32"`), execute `robocopy` with `/MIR /FFT /Z /NP /NDL /NJS /NJH`.
    - On non-Windows platforms, mirror files using timestamp comparison and `shutil.copy2`.
  - Handle exceptions gracefully, clean up temporary staging files on error, and return exit code 1 on failure.

### 2.3 Automated Test Suite for Migration and Backup Helpers
- Create [`api/tests/test_deployment_scripts.py`](file:///D:/src/personal/wrangler/api/tests/test_deployment_scripts.py):
  - Test `check_migrations`:
    - Test exit code 0 when database revision matches Alembic head.
    - Test exit code 2 when database has pending migrations or lacks `alembic_version` table.
    - Test exit code 1 on database connection error.
  - Test `wal_backup`:
    - Test return 0 when `BACKUP_DIR` is unset.
    - Test return 0, creation of atomic `wrangler.db` snapshot, and mirrored receipts when `BACKUP_DIR` is set.
    - Test cleanup of temporary `.tmp` files and exit code 1 on snapshot execution error.

---

## Phase 3: Production Runtime Launcher & Release Packaging Pipeline

*Goal:* Deliver production PowerShell automation scripts for interactive server execution (`prod.ps1`) and idempotent code packaging (`release.ps1`).

### 3.1 Implement Production Runtime Launcher Script
- Create [`prod.ps1`](file:///D:/src/personal/wrangler/prod.ps1) at repository root:
  - Define parameter contract: `[int]$Port = 8000`, `[string]$HostAddress = "0.0.0.0"`, `[switch]$Migrate`, `[switch]$SkipMigration`.
  - Validate presence of `uv` in `PATH`.
  - Run migration pre-flight check using `uv run --directory $ApiDir python scripts/check_migrations.py`.
  - Handle exit code 2 (pending migrations):
    - If `-Migrate` passed, run `alembic upgrade head`.
    - If not `-SkipMigration`, prompt user `Pending database migrations detected. Apply them now? [Y/n]`.
    - If confirmed, run `alembic upgrade head`; abort startup on migration failure.
  - Handle exit code 0: display schema up-to-date confirmation.
  - Launch production Uvicorn server in single process (no `--reload`) within a `try ... finally` block.
  - Set `$ServerStartedCleanly = $true` upon successful invocation.
  - In `finally` block:
    - If `$ServerStartedCleanly`: invoke `api/scripts/wal_backup.py` to snapshot database and mirror receipts.
    - If `$ServerStartedCleanly -eq $false`: skip backup execution to protect existing backups from corrupted startup state.

### 3.2 Implement Release Packaging Script
- Create [`release.ps1`](file:///D:/src/personal/wrangler/release.ps1) at repository root:
  - Define parameter contract: `[string]$TargetDir = "D:\Wrangler"`, `[switch]$SkipBuild`.
  - Validate presence of `uv` and `pnpm` in `PATH`.
  - Compile frontend SPA using `pnpm --filter web build` unless `-SkipBuild` is specified; verify `web/dist/index.html` exists.
  - Provision target directory structure: `$TargetDir\api` and `$TargetDir\web`.
  - Copy runtime backend code and assets using `robocopy`:
    - `api\src` -> `$TargetDir\api\src`
    - `api\alembic` -> `$TargetDir\api\alembic`
    - `api\scripts` -> `$TargetDir\api\scripts`
  - Copy root backend configuration files: `api\alembic.ini`, `api\pyproject.toml`, `api\uv.lock`.
  - Copy compiled frontend assets: `web\dist` -> `$TargetDir\web\dist`.
  - Copy production launcher: `prod.ps1` -> `$TargetDir\prod.ps1`.
  - Strictly enforce isolation: never copy, create, or modify `.env` or `data/` in `$TargetDir`.
  - Run virtualenv synchronization: `uv sync --directory (Join-Path $TargetDir "api") --no-dev`.

### 3.3 Automated Test Suite for Release Pipeline & Packaging Isolation
- Create [`api/tests/test_release_packaging.py`](file:///D:/src/personal/wrangler/api/tests/test_release_packaging.py):
  - Verify script presence: ensure `prod.ps1` and `release.ps1` exist at repository root.
  - Test `release.ps1` packaging execution against a temporary directory:
    - Pre-create mock `.env` and `data/test.db` in target directory.
    - Execute `release.ps1` with `-SkipBuild` targeting the temporary directory.
    - Verify target contains expected files: `api/src`, `api/alembic`, `api/scripts`, `web/dist`, and `prod.ps1`.
    - Verify pre-existing `.env` and `data/test.db` are completely untouched and unmodified.
