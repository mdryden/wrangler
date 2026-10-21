---
status: Implemented
subsystems:
  - Platform
amendments: []
supersedes: null
superseded_by: null
---

# Specification Amendment 1: Scheduled Daily Backups, Direct Receipt Storage & DATA_DIR Deprecation

**Target Specification:** [`specs/10-production-deployment/spec.md`](file:///D:/src/personal/wrangler/specs/10-production-deployment/spec.md)  
**Status:** Implemented  
**Subsystems:** Platform & Shell  
**Date:** 2026-10-21  

---

## 1. Context & Motivation

In [`specs/10-production-deployment/spec.md`](file:///D:/src/personal/wrangler/specs/10-production-deployment/spec.md), database and receipt backups were designed to execute exclusively within the `finally` clean-exit trap in [`prod.ps1`](file:///D:/src/personal/wrangler/prod.ps1) upon receiving `Ctrl+C`.

This shutdown-only backup model introduced two operational issues:

1. **Vulnerability During Long-Running Sessions:**  
   If Wrangler is left running continuously for days or weeks (e.g., hosted 24/7 on a home server or workstation), no backups occur. A machine reboot, unexpected power loss, or unhandled system crash leaves all database mutations and uploaded receipts since the last shutdown unbacked-up.
2. **Redundant Local Receipt Storage (`DATA_DIR`):**  
   Spec 10 introduced dual-location storage for receipts (`DATA_DIR/receipts` mirrored to `BACKUP_DIR/receipts` via robocopy). Unlike SQLite, which requires atomic snapshots to prevent WAL lock contention and cloud sync corruption, receipts are immutable static files (PDFs and images). Storing receipts in `DATA_DIR` and mirroring them on shutdown causes duplicate disk usage, configuration ambiguity (two similar data path variables: `DATA_DIR` and `BACKUP_DIR`), and delayed cloud synchronization.

This amendment defines the architectural changes to:
- Deprecate and eliminate `DATA_DIR`.
- Store receipts directly in `<BACKUP_DIR>/receipts` in production for instant cloud synchronization.
- Implement an in-process, headless daily backup scheduler executing at **2:00 AM** to snapshot the SQLite database atomically.
- Retain the clean-exit shutdown snapshot in `prod.ps1` to protect short bookkeeping sessions.

---

## 2. Summary of Architectural Changes

| Area | Prior Architecture (Spec 10) | Amended Architecture (Amendment 1) |
| :--- | :--- | :--- |
| **Backup Trigger** | Shutdown only (`Ctrl+C` in `prod.ps1`). | Dual: **Daily at 02:00 AM** (in-process scheduler) **+ Shutdown** (`Ctrl+C`). |
| **Scheduler Engine** | None. | In-process asynchronous task in FastAPI `lifespan`. |
| **Receipt Storage** | Dual: Primary in `DATA_DIR/receipts`, mirrored to `BACKUP_DIR/receipts` on exit. | Single: Direct write to `<BACKUP_DIR>/receipts` in production (`./receipts` in dev). |
| **Receipt Mirroring** | Robocopy `/MIR` on exit. | **Removed.** Receipts sync immediately via Google Drive desktop client upon upload. |
| **Environment Config** | Both `DATA_DIR` and `BACKUP_DIR` defined in `.env`. | `DATA_DIR` **eliminated**. Only `BACKUP_DIR` configured. |
| **Database Path** | Derived from `DATA_DIR/wrangler.db` or `DATABASE_URL`. | Standard default path (`sqlite:///./wrangler.db` in API root). |
| **Database Snapshot** | `VACUUM INTO '<BACKUP_DIR>/wrangler.db'` on exit only. | `VACUUM INTO '<BACKUP_DIR>/wrangler.db'` at 2:00 AM daily and on clean exit. |

---

## 3. Configuration & Data Model Specifications

### 3.1 Backend Settings (`api/src/core/config.py`)

1. **Remove `DATA_DIR`:**  
   Remove `DATA_DIR: Path | None = None` and its derivation logic in `@model_validator(mode="after")`.
2. **Add `BACKUP_SCHEDULE_TIME`:**  
   Configurable daily backup schedule time in `HH:MM` 24-hour format (defaults to `"02:00"`).
3. **Dynamic Receipt Storage Path Derivation:**  
   - If `BACKUP_DIR` is set (production environment):
     - `RECEIPT_STORAGE_DIR` defaults to `(self.BACKUP_DIR / "receipts").resolve()`.
   - If `BACKUP_DIR` is unset (development environment):
     - `RECEIPT_STORAGE_DIR` defaults to `Path("receipts").resolve()`.
   - Explicit `RECEIPT_STORAGE_DIR` overrides in `.env` remain honored.
4. **Receipt Directory Initialization:**  
   Ensure `RECEIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)` continues to execute on config initialization.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_API_DIR / ".env"),
            str(_ROOT_DIR / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google Drive / External Cloud Backup Directory (Required in production)
    BACKUP_DIR: Path | None = None

    # Scheduled Daily Backup Time (24h format, default 02:00 AM)
    BACKUP_SCHEDULE_TIME: str = "02:00"

    # Receipt Storage (Defaults to BACKUP_DIR/receipts if BACKUP_DIR set, else ./receipts)
    RECEIPT_STORAGE_DIR: Path = Path("receipts").resolve()

    # Database Connection String
    DATABASE_URL: str = "sqlite:///./wrangler.db"

    # ... remaining settings unchanged ...

    @model_validator(mode="after")
    def resolve_paths(self) -> "Settings":
        if self.BACKUP_DIR is not None:
            self.BACKUP_DIR = Path(self.BACKUP_DIR).expanduser().resolve()
            # Default receipt storage directly into the cloud backup folder
            if Path(self.RECEIPT_STORAGE_DIR).resolve() == Path("receipts").resolve():
                self.RECEIPT_STORAGE_DIR = (self.BACKUP_DIR / "receipts").resolve()

        self.RECEIPT_STORAGE_DIR = Path(self.RECEIPT_STORAGE_DIR).expanduser().resolve()
        self.RECEIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return self
```

### 3.2 Production `.env` Contract (`D:\Wrangler\.env`)

The production `.env` is simplified by removing `DATA_DIR`:

```bash
# ==============================================================================
# Wrangler Production Configuration (D:\Wrangler\.env)
# ==============================================================================

# Google Drive Cloud Backup Destination (Receipts and DB snapshots written here)
BACKUP_DIR=C:/Users/mjdry/Google Drive/WranglerBackups

# Scheduled Daily Backup Time (24-hour local time, default 02:00)
BACKUP_SCHEDULE_TIME=02:00

# Security & Authentication (Required)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-to-a-secure-production-password
JWT_SECRET_KEY=change-to-a-secure-random-32-character-secret-key
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Network & MCP Integration
MCP_API_KEY=your-mcp-key-if-using-lan-clients

# AI Parsing
AI_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key
```

---

## 4. Backend Backup Service & Scheduler Architecture

### 4.1 Core Backup Service (`api/src/services/backup.py`)

Encapsulate the SQLite atomic snapshot routine in a shared service module callable by both the background scheduler and CLI scripts:

```python
"""Atomic SQLite database snapshot service."""

import logging
from pathlib import Path
from sqlalchemy import text
from core.config import settings
from database import engine

logger = logging.getLogger("wrangler.backup")


def execute_database_snapshot() -> bool:
    """Executes atomic SQLite VACUUM INTO '<BACKUP_DIR>/wrangler.db'.
    
    Uses an atomic staging file (wrangler.db.tmp) to avoid leaving corrupted
    or partial files if interrupted.
    """
    if not settings.BACKUP_DIR:
        logger.warning("BACKUP_DIR is not configured. Skipping database snapshot.")
        return False

    backup_dir = settings.BACKUP_DIR.expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    if not settings.DATABASE_URL.startswith("sqlite"):
        logger.info("DATABASE_URL is not SQLite. Skipping SQLite VACUUM snapshot.")
        return True

    target_db = backup_dir / "wrangler.db"
    temp_target_db = backup_dir / "wrangler.db.tmp"

    if temp_target_db.exists():
        temp_target_db.unlink()

    try:
        with engine.connect() as conn:
            conn.execute(text(f"VACUUM INTO '{temp_target_db.as_posix()}';"))

        if target_db.exists():
            target_db.unlink()
        temp_target_db.rename(target_db)

        logger.info(f"SQLite snapshot successfully saved to: {target_db}")
        return True

    except Exception as exc:
        logger.error(f"Error executing SQLite snapshot: {exc}", exc_info=True)
        if temp_target_db.exists():
            try:
                temp_target_db.unlink()
            except OSError:
                pass
        return False
```

### 4.2 Asynchronous Daily Scheduler (`api/src/services/backup_scheduler.py`)

A lightweight in-process scheduler managed as an `asyncio` task:

1. **Next Target Calculation:**  
   Parses `settings.BACKUP_SCHEDULE_TIME` (`HH:MM`). Calculates the number of seconds until that clock time occurs next in local time (if already passed today, schedules for tomorrow).
2. **Non-Blocking Sleep:**  
   Sleeps via `asyncio.sleep` until the scheduled target time.
3. **Off-Thread Execution:**  
   Dispatches `execute_database_snapshot` to a worker thread via `asyncio.to_thread` to ensure SQLite disk I/O does not block the FastAPI event loop.
4. **Resilience:**  
   Wraps execution in a broad `try/except` block to ensure that an I/O error or permission issue never crashes the background loop or the web server.
5. **Clean Shutdown:**  
   Catches `asyncio.CancelledError` on server termination to exit immediately without hanging.

```python
"""In-process daily backup scheduler."""

import asyncio
from datetime import datetime, time, timedelta
import logging
from core.config import settings
from services.backup import execute_database_snapshot

logger = logging.getLogger("wrangler.backup")


def get_seconds_until_next_run(target_time_str: str) -> float:
    """Calculates seconds until the next occurrence of target_time_str (HH:MM)."""
    try:
        hour_str, minute_str = target_time_str.strip().split(":")
        target_t = time(hour=int(hour_str), minute=int(minute_str))
    except Exception:
        logger.warning(f"Invalid BACKUP_SCHEDULE_TIME '{target_time_str}'. Defaulting to 02:00.")
        target_t = time(hour=2, minute=0)

    now = datetime.now()
    target_dt = datetime.combine(now.date(), target_t)
    if target_dt <= now:
        target_dt += timedelta(days=1)

    return (target_dt - now).total_seconds()


async def run_backup_scheduler() -> None:
    """Background loop that executes execute_database_snapshot() daily at the configured time."""
    if not settings.BACKUP_DIR:
        logger.info("BACKUP_DIR not set. Background backup scheduler is disabled.")
        return

    logger.info(f"Backup scheduler started. Daily snapshot scheduled for {settings.BACKUP_SCHEDULE_TIME}.")

    try:
        while True:
            sleep_seconds = get_seconds_until_next_run(settings.BACKUP_SCHEDULE_TIME)
            next_run_dt = datetime.now() + timedelta(seconds=sleep_seconds)
            logger.info(f"Next scheduled database backup at: {next_run_dt.strftime('%Y-%m-%d %H:%M:%S')}")

            await asyncio.sleep(sleep_seconds)

            logger.info("Triggering scheduled daily database backup...")
            success = await asyncio.to_thread(execute_database_snapshot)
            if success:
                logger.info("Scheduled daily database backup completed successfully.")
            else:
                logger.error("Scheduled daily database backup failed.")

    except asyncio.CancelledError:
        logger.info("Backup scheduler received cancellation signal. Stopping.")
```

### 4.3 Lifespan Management (`api/src/main.py`)

Wire the scheduler into FastAPI's `lifespan` context:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure receipt storage directory exists on startup
    settings.RECEIPT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    if not settings.BACKUP_DIR and not os.getenv("BACKUP_DIR"):
        print("\n" + "=" * 64)
        print(" WARNING: BACKUP_DIR is not configured!")
        print(" Automatic database snapshots on exit will be skipped.")
        print(" Set BACKUP_DIR in your .env to safeguard your financial data.")
        print("=" * 64 + "\n")

    # Start background backup scheduler task if BACKUP_DIR is configured
    scheduler_task = None
    if settings.BACKUP_DIR:
        scheduler_task = asyncio.create_task(run_backup_scheduler())

    session_mgr = getattr(mcp._lowlevel_server, "_session_manager", None)
    if session_mgr is not None:
        session_mgr._has_started = False
    try:
        async with mcp_stream_app.router.lifespan_context(mcp_stream_app):
            yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        if session_mgr is not None:
            session_mgr._has_started = False
```

---

## 5. Deployment & Script Updates

### 5.1 CLI Snapshot Helper (`api/scripts/wal_backup.py`)

Refactor `api/scripts/wal_backup.py` to delegate to `services.backup.execute_database_snapshot()`. Remove all `robocopy` and receipt-copying code:

```python
"""CLI wrapper for executing an atomic SQLite database snapshot."""

import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from services.backup import execute_database_snapshot


def run_backup() -> int:
    success = execute_database_snapshot()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(run_backup())
```

### 5.2 Production Runtime Launcher (`prod.ps1`)

Update `prod.ps1`:
1. **Pre-flight Check:** Verify `BACKUP_DIR` exists in `.env`.
2. **Shutdown Hook Message:** Update output text from `"Executing clean SQLite snapshot and mirroring receipts..."` to `"Executing clean SQLite snapshot..."`.

---

## 6. Architectural Invariant & Risk Review

| Concern / Invariant | Status | Mitigation |
| :--- | :--- | :--- |
| **No Duplicate Receipt Storage** | Resolved | Receipts are saved exclusively to `RECEIPT_STORAGE_DIR` (which resolves to `<BACKUP_DIR>/receipts`). `robocopy /MIR` is eliminated. |
| **Instant Cloud Sync for Receipts** | Resolved | Newly uploaded receipts (via manual upload or AI parser) appear in Google Drive immediately without waiting for backup schedules or server shutdown. |
| **WAL File & Sync Locks** | Maintained | Live SQLite database remains local (`sqlite:///./wrangler.db`). Google Drive never interacts with the live database or its `.wal`/`.shm` files; it only syncs the atomic static copy (`<BACKUP_DIR>/wrangler.db`). |
| **Event Loop Blocking** | Maintained | `asyncio.to_thread` ensures the `VACUUM INTO` disk write runs in a worker thread, preventing HTTP/MCP request starvation. |
| **Application Crash Safety** | Maintained | The scheduler loop catches all exceptions and logs them; database backup errors cannot crash the Uvicorn web server. |
| **Short-Session Safety** | Maintained | Stopping Wrangler with `Ctrl+C` immediately triggers `wal_backup.py`, ensuring sessions ended before 02:00 AM are backed up. |

---

## 7. Verification & Acceptance Scenarios

1. **Settings Path Resolution:**
   - In dev (no `BACKUP_DIR`): `settings.RECEIPT_STORAGE_DIR` resolves to `./receipts`.
   - In prod (`BACKUP_DIR="D:/Backups"`): `settings.RECEIPT_STORAGE_DIR` resolves to `D:/Backups/receipts`.
   - `DATA_DIR` is no longer recognized or required by `Settings`.
2. **Direct Receipt Write:**
   - Upload a receipt via `POST /api/receipts/upload` or AI intake.
   - Assert file is written directly inside `<BACKUP_DIR>/receipts/`.
   - Assert `GET /api/receipts/{id}/file` streams the file cleanly.
3. **Scheduler Lifecycle & Timing:**
   - Start FastAPI with `BACKUP_DIR` set.
   - Verify log outputs: `"Next scheduled database backup at: YYYY-MM-DD 02:00:00"`.
   - Verify that upon graceful FastAPI shutdown, the task cancels cleanly without traceback.
4. **Scheduled Execution:**
   - Fast-forward time / configure `BACKUP_SCHEDULE_TIME` to current time + 10 seconds.
   - Verify `execute_database_snapshot` runs via `asyncio.to_thread`.
   - Assert `<BACKUP_DIR>/wrangler.db` is updated with current data and readable via `sqlite3`.
5. **Clean Exit Trap (`prod.ps1`):**
   - Start server with `./prod.ps1`.
   - Terminate with `Ctrl+C`.
   - Verify `wal_backup.py` executes successfully without attempting receipt robocopy.
