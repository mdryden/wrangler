# Implementation Plan Amendment 1: Scheduled Daily Backups, Direct Receipt Storage & DATA_DIR Deprecation

This implementation plan defines the deliverables and engineering tasks for transitioning Wrangler to scheduled headless daily database snapshots, direct receipt storage in the external cloud backup directory, complete removal of `DATA_DIR`, and elimination of redundant receipt mirroring on shutdown, as specified in [`specs/10-production-deployment/spec-amendment1.md`](file:///D:/src/personal/wrangler/specs/10-production-deployment/spec-amendment1.md).

The plan is organized into sequential phases and atomic implementation tasks. Each task specifies concrete deliverables and automated unit or integration test coverage adhering to project conventions and development standards defined in [`AGENTS.md`](file:///D:/src/personal/wrangler/AGENTS.md).

---

## Phase 1: Configuration Refactoring & Direct Cloud Receipt Storage

*Goal:* Eliminate the redundant `DATA_DIR` configuration setting, configure the daily backup schedule time setting, and derive receipt storage directly into the cloud backup destination when configured.

### 1.1 Refactor Backend Settings (`api/src/core/config.py`)
- In [`api/src/core/config.py`](file:///D:/src/personal/wrangler/api/src/core/config.py):
  - Remove `DATA_DIR: Path | None = None` from [`Settings`](file:///D:/src/personal/wrangler/api/src/core/config.py).
  - Add `BACKUP_SCHEDULE_TIME: str = "02:00"` to [`Settings`](file:///D:/src/personal/wrangler/api/src/core/config.py).
  - Keep `DATABASE_URL: str = "sqlite:///./wrangler.db"` as the standard default connection string.
  - Keep `RECEIPT_STORAGE_DIR: Path = Path("receipts").resolve()` as the default field value.
  - Refactor `@model_validator(mode="after")` method `resolve_paths(self) -> Settings`:
    - Remove all code referencing `self.DATA_DIR` and its path mutations.
    - If `self.BACKUP_DIR is not None`:
      - Resolve `self.BACKUP_DIR = Path(self.BACKUP_DIR).expanduser().resolve()`.
      - If `Path(self.RECEIPT_STORAGE_DIR).resolve() == Path("receipts").resolve()`:
        - Automatically route receipts to the cloud folder: `self.RECEIPT_STORAGE_DIR = (self.BACKUP_DIR / "receipts").resolve()`.
    - Resolve `self.RECEIPT_STORAGE_DIR = Path(self.RECEIPT_STORAGE_DIR).expanduser().resolve()`.
    - Ensure directory exists: `self.RECEIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)`.
    - Return `self`.
  - Maintain formatting standards and relative imports.

### 1.2 Update Configuration Automated Test Suite (`api/tests/test_production_config_and_spa.py`)
- In [`api/tests/test_production_config_and_spa.py`](file:///D:/src/personal/wrangler/api/tests/test_production_config_and_spa.py):
  - Remove deprecated tests `test_data_dir_dynamic_path_resolution` and `test_data_dir_explicit_overrides_preserved`.
  - Add `test_receipt_storage_path_resolution_default_dev`:
    - Initialize `Settings()` with no `BACKUP_DIR`.
    - Assert `RECEIPT_STORAGE_DIR` resolves to `./receipts` and directory exists.
    - Assert `BACKUP_SCHEDULE_TIME` defaults to `"02:00"`.
    - Assert `DATABASE_URL` defaults to `"sqlite:///./wrangler.db"`.
  - Add `test_receipt_storage_path_resolution_production`:
    - Initialize `Settings(BACKUP_DIR=custom_backup_path)` with a temporary path.
    - Assert `RECEIPT_STORAGE_DIR` resolves to `<BACKUP_DIR>/receipts` and directory exists.
  - Add `test_receipt_storage_path_explicit_override`:
    - Initialize `Settings(BACKUP_DIR=custom_backup_path, RECEIPT_STORAGE_DIR=custom_receipt_path)`.
    - Assert `RECEIPT_STORAGE_DIR` retains `custom_receipt_path` and directory exists.
  - Add `test_backup_schedule_time_custom`:
    - Initialize `Settings(BACKUP_SCHEDULE_TIME="03:45")`.
    - Assert `BACKUP_SCHEDULE_TIME` equals `"03:45"`.

---

## Phase 2: Core SQLite Backup Service & Headless Daily Scheduler

*Goal:* Encapsulate atomic SQLite snapshots into a shared backend service, implement an asynchronous background daily scheduler in FastAPI, and verify resilience against failures and cancellation.

### 2.1 Implement Core SQLite Database Snapshot Service (`api/src/services/backup.py`)
- Create [`api/src/services/backup.py`](file:///D:/src/personal/wrangler/api/src/services/backup.py):
  - Set logger name to `"wrangler.backup"`.
  - Implement `execute_database_snapshot() -> bool`:
    - If `not settings.BACKUP_DIR`:
      - Log warning `"BACKUP_DIR is not configured. Skipping database snapshot."` and return `False`.
    - Expand and resolve `backup_dir = settings.BACKUP_DIR.expanduser().resolve()`.
    - Ensure backup directory exists via `backup_dir.mkdir(parents=True, exist_ok=True)`.
    - If `not settings.DATABASE_URL.startswith("sqlite")`:
      - Log info `"DATABASE_URL is not SQLite. Skipping SQLite VACUUM snapshot."` and return `True`.
    - Target paths: `target_db = backup_dir / "wrangler.db"` and temporary file `temp_target_db = backup_dir / "wrangler.db.tmp"`.
    - Unlink `temp_target_db` if it already exists.
    - Execute within a `try` block:
      - Connect with SQLAlchemy engine: `with engine.connect() as conn:`.
      - Execute SQLite atomic copy: `conn.execute(text(f"VACUUM INTO '{temp_target_db.as_posix()}';"))`.
      - If `target_db.exists()`, unlink it.
      - Atomically rename `temp_target_db.rename(target_db)`.
      - Log info `"SQLite snapshot successfully saved to: {target_db}"` and return `True`.
    - Execute within an `except Exception as exc` block:
      - Log error `"Error executing SQLite snapshot: {exc}"` with `exc_info=True`.
      - Safely clean up `temp_target_db` if it exists.
      - Return `False`.

### 2.2 Implement Asynchronous Daily Backup Scheduler (`api/src/services/backup_scheduler.py`)
- Create [`api/src/services/backup_scheduler.py`](file:///D:/src/personal/wrangler/api/src/services/backup_scheduler.py):
  - Set logger name to `"wrangler.backup"`.
  - Implement helper `get_seconds_until_next_run(target_time_str: str) -> float`:
    - Parse `"HH:MM"` into hour and minute components.
    - If invalid or unparseable, log warning `"Invalid BACKUP_SCHEDULE_TIME '{target_time_str}'. Defaulting to 02:00."` and use `time(hour=2, minute=0)`.
    - Compare `target_dt = datetime.combine(now.date(), target_t)` with `now = datetime.now()`.
    - If `target_dt <= now`, increment `target_dt += timedelta(days=1)`.
    - Return `(target_dt - now).total_seconds()`.
  - Implement async worker `async def run_backup_scheduler() -> None`:
    - If `not settings.BACKUP_DIR`:
      - Log info `"BACKUP_DIR not set. Background backup scheduler is disabled."` and return.
    - Log info `"Backup scheduler started. Daily snapshot scheduled for {settings.BACKUP_SCHEDULE_TIME}."`
    - Loop `while True` within a `try` block:
      - Calculate `sleep_seconds = get_seconds_until_next_run(settings.BACKUP_SCHEDULE_TIME)`.
      - Compute `next_run_dt = datetime.now() + timedelta(seconds=sleep_seconds)`.
      - Log info `"Next scheduled database backup at: {next_run_dt.strftime('%Y-%m-%d %H:%M:%S')}"`.
      - Await `asyncio.sleep(sleep_seconds)`.
      - Log info `"Triggering scheduled daily database backup..."`.
      - Execute snapshot off the main thread: `success = await asyncio.to_thread(execute_database_snapshot)`.
      - Log info `"Scheduled daily database backup completed successfully."` on `success == True`.
      - Log error `"Scheduled daily database backup failed."` on `success == False`.
    - Catch `asyncio.CancelledError`:
      - Log info `"Backup scheduler received cancellation signal. Stopping."` and exit cleanly.

### 2.3 Integrate Scheduler into FastAPI Application Lifespan (`api/src/main.py`)
- In [`api/src/main.py`](file:///D:/src/personal/wrangler/api/src/main.py):
  - Import `asyncio`.
  - Import `run_backup_scheduler` from `services.backup_scheduler`.
  - Update `lifespan(app: FastAPI)`:
    - Update the missing `BACKUP_DIR` warning banner output:
      - Change `"Automatic database snapshots & receipt mirroring on exit will be skipped."`
      - To `"Automatic database snapshots on exit will be skipped."`
    - Initialize `scheduler_task = None`.
    - If `settings.BACKUP_DIR`:
      - Create background task: `scheduler_task = asyncio.create_task(run_backup_scheduler())`.
    - In `finally` block:
      - If `scheduler_task is not None`:
        - `scheduler_task.cancel()`
        - Await task completion catching `asyncio.CancelledError`.

### 2.4 Automated Test Suite for Backup Service and Scheduler (`api/tests/test_backup_service_and_scheduler.py`)
- Create [`api/tests/test_backup_service_and_scheduler.py`](file:///D:/src/personal/wrangler/api/tests/test_backup_service_and_scheduler.py):
  - Test `execute_database_snapshot`:
    - Verify returns `False` when `settings.BACKUP_DIR` is `None`.
    - Verify returns `True` without SQLite execution when `settings.DATABASE_URL` starts with `postgresql`.
    - Verify returns `True`, generates valid SQLite database file at `<BACKUP_DIR>/wrangler.db`, and leaves no `.tmp` file when successful.
    - Verify error handling: patch `engine.connect` to raise `OperationalError`, assert returns `False`, and assert `.tmp` staging file is unlinked.
  - Test `get_seconds_until_next_run`:
    - Verify calculates correct seconds delta for future target time today.
    - Verify rolls over to tomorrow (+24 hours) for target time earlier than current time today.
    - Verify invalid format strings (e.g. `"bad:time"`, `"99:99"`, `""`) default gracefully to 02:00 calculation without exception.
  - Test `run_backup_scheduler`:
    - Verify immediate return when `settings.BACKUP_DIR` is `None`.
    - Verify execution cycle: patch `get_seconds_until_next_run` to return 0.01 seconds, patch `execute_database_snapshot` to record calls, allow loop to tick, and cancel task cleanly via `asyncio.CancelledError`.
    - Verify scheduler loop survives and continues running when `execute_database_snapshot` raises or returns `False`.
  - Test FastAPI `lifespan` background task lifecycle:
    - Verify background task is created and runs when `settings.BACKUP_DIR` is set.
    - Verify background task cancels without traceback upon lifespan shutdown.
    - Verify background task is not created when `settings.BACKUP_DIR` is `None`.

---

## Phase 3: Deployment Scripts & Test Modernization

*Goal:* Streamline the CLI backup utility to delegate to the new backup service, remove obsolete robocopy receipt mirroring, update the production runtime launcher, and eliminate obsolete test cases.

### 3.1 Streamline CLI Snapshot Script (`api/scripts/wal_backup.py`)
- In [`api/scripts/wal_backup.py`](file:///D:/src/personal/wrangler/api/scripts/wal_backup.py):
  - Replace entire script implementation with a lightweight CLI entry point:
    - Add `src` directory to `sys.path`.
    - Import `execute_database_snapshot` from `services.backup`.
    - Implement `run_backup() -> int`:
      - Execute `success = execute_database_snapshot()`.
      - Return `0 if success else 1`.
    - Invoke `sys.exit(run_backup())` in `if __name__ == "__main__":`.
  - Remove all robocopy subprocess execution, filesystem traversal, timestamp checks, and manual SQL connection code.

### 3.2 Update Production Server Runtime Launcher (`prod.ps1`)
- In [`prod.ps1`](file:///D:/src/personal/wrangler/prod.ps1):
  - Update pre-flight warning message in section 2 ("Backup Destination Verification"):
    - Change `"Automatic database snapshots & receipt mirroring on exit will be skipped."`
    - To `"Automatic database snapshots on exit will be skipped."`
  - Update shutdown trap message in `finally` block:
    - Change `"Executing clean SQLite snapshot and mirroring receipts..."`
    - To `"Executing clean SQLite snapshot..."`

### 3.3 Modernize Deployment Scripts Test Suite (`api/tests/test_deployment_scripts.py`)
- In [`api/tests/test_deployment_scripts.py`](file:///D:/src/personal/wrangler/api/tests/test_deployment_scripts.py):
  - Update `test_wal_backup_noop_when_backup_dir_unset`:
    - Verify `run_backup()` returns exit code `1` (or logs warning) when `BACKUP_DIR` is unset, reflecting that a requested snapshot cannot be performed.
  - Update `test_wal_backup_success_from_settings` and `test_wal_backup_success`:
    - Assert `run_backup()` returns `0`.
    - Assert `<BACKUP_DIR>/wrangler.db` is generated.
    - Remove all assertions checking `<BACKUP_DIR>/receipts` (receipt mirroring eliminated from backup script).
  - Update `test_wal_backup_error_handling_and_tmp_cleanup`:
    - Patch `execute_database_snapshot` to return `False`, assert `run_backup()` returns `1`.
