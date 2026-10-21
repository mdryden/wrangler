import asyncio
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import main
from core.config import settings
from database import engine
from services.backup import execute_database_snapshot
from services.backup_scheduler import get_seconds_until_next_run, run_backup_scheduler


def test_execute_database_snapshot_no_backup_dir(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "BACKUP_DIR", None)
    assert execute_database_snapshot() is False


def test_execute_database_snapshot_non_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_dir = tmp_path / "backup"
    monkeypatch.setattr(settings, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://user:pass@localhost:5432/db")

    assert execute_database_snapshot() is True
    assert not (backup_dir / "wrangler.db").exists()


def test_execute_database_snapshot_sqlite_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_dir = tmp_path / "backup"
    monkeypatch.setattr(settings, "BACKUP_DIR", backup_dir)

    success = execute_database_snapshot()
    assert success is True

    target_db = backup_dir / "wrangler.db"
    assert target_db.is_file()
    assert not (backup_dir / "wrangler.db.tmp").exists()

    # Verify that the generated database file is valid and queryable
    conn = sqlite3.connect(target_db)
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    assert cursor.fetchone() == (1,)
    conn.close()


def test_execute_database_snapshot_error_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    temp_file = backup_dir / "wrangler.db.tmp"
    temp_file.write_text("dummy staging content", encoding="utf-8")

    monkeypatch.setattr(settings, "BACKUP_DIR", backup_dir)

    def mock_connect(*args, **kwargs):
        raise OperationalError("mock operational error", params=None, orig=Exception("disk error"))

    monkeypatch.setattr(engine, "connect", mock_connect)

    assert execute_database_snapshot() is False
    assert not temp_file.exists()


def test_get_seconds_until_next_run():
    now = datetime.now()

    # Target 1 hour in the future today
    future_time = (now + timedelta(hours=1)).strftime("%H:%M")
    seconds = get_seconds_until_next_run(future_time)
    assert 3500 < seconds <= 3600

    # Target 1 hour in the past today -> rolls over to tomorrow
    past_time = (now - timedelta(hours=1)).strftime("%H:%M")
    seconds_past = get_seconds_until_next_run(past_time)
    assert 22 * 3600 < seconds_past <= 24 * 3600

    # Invalid time strings should gracefully default to "02:00" calculation
    invalid_inputs = ["bad:time", "99:99", "", "abc", "25:00"]
    expected_default_seconds = get_seconds_until_next_run("02:00")
    for bad in invalid_inputs:
        result = get_seconds_until_next_run(bad)
        # Should match "02:00" calculation within small timing tolerance
        assert abs(result - expected_default_seconds) < 2.0


@pytest.mark.anyio
async def test_run_backup_scheduler_no_backup_dir(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "BACKUP_DIR", None)
    # When BACKUP_DIR is not set, run_backup_scheduler should return immediately
    await run_backup_scheduler()


@pytest.mark.anyio
async def test_run_backup_scheduler_execution_and_cancellation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_dir = tmp_path / "backup"
    monkeypatch.setattr(settings, "BACKUP_DIR", backup_dir)

    monkeypatch.setattr("services.backup_scheduler.get_seconds_until_next_run", lambda _target: 0.01)

    calls = []

    def mock_snapshot():
        calls.append(True)
        return True

    monkeypatch.setattr("services.backup_scheduler.execute_database_snapshot", mock_snapshot)

    task = asyncio.create_task(run_backup_scheduler())
    await asyncio.sleep(0.05)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(calls) >= 1


@pytest.mark.anyio
async def test_run_backup_scheduler_resilience_to_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_dir = tmp_path / "backup"
    monkeypatch.setattr(settings, "BACKUP_DIR", backup_dir)

    monkeypatch.setattr("services.backup_scheduler.get_seconds_until_next_run", lambda _target: 0.01)

    calls = 0

    def failing_snapshot():
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr("services.backup_scheduler.execute_database_snapshot", failing_snapshot)

    task = asyncio.create_task(run_backup_scheduler())
    await asyncio.sleep(0.05)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    # Scheduler loop survived and continued looping despite failure
    assert calls >= 2


def test_lifespan_backup_scheduler_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    backup_dir = tmp_path / "backup"
    monkeypatch.setattr(settings, "BACKUP_DIR", backup_dir)

    scheduler_started = False

    async def mock_scheduler():
        nonlocal scheduler_started
        scheduler_started = True
        try:
            while True:
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            pass

    monkeypatch.setattr("main.run_backup_scheduler", mock_scheduler)

    with TestClient(main.app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert scheduler_started is True


def test_lifespan_backup_scheduler_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "BACKUP_DIR", None)

    scheduler_started = False

    async def mock_scheduler():
        nonlocal scheduler_started
        scheduler_started = True

    monkeypatch.setattr("main.run_backup_scheduler", mock_scheduler)

    with TestClient(main.app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert scheduler_started is False
