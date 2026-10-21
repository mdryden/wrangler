"""Atomic SQLite database snapshot service."""

import logging

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
