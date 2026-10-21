"""In-process daily backup scheduler."""

import asyncio
import logging
from datetime import datetime, time, timedelta

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
