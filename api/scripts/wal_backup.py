"""Performs atomic SQLite VACUUM INTO snapshot and mirrors receipts to BACKUP_DIR."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import text

from core.config import settings
from database import engine


def run_backup() -> int:
    backup_dir_str = os.getenv("BACKUP_DIR")
    if not backup_dir_str:
        print("BACKUP_DIR is not set in environment. Skipping backup snapshot.")
        return 0

    backup_dir = Path(backup_dir_str).expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    # 1. Atomic SQLite Snapshot via VACUUM INTO
    if settings.DATABASE_URL.startswith("sqlite"):
        target_db = backup_dir / "wrangler.db"
        temp_target_db = backup_dir / "wrangler.db.tmp"

        if temp_target_db.exists():
            temp_target_db.unlink()

        try:
            with engine.connect() as conn:
                # SQLite VACUUM INTO creates a crash-consistent, complete single-file copy
                conn.execute(text(f"VACUUM INTO '{temp_target_db.as_posix()}';"))

            # Atomically replace destination file
            if target_db.exists():
                target_db.unlink()
            temp_target_db.rename(target_db)
            print(f"SQLite snapshot saved to: {target_db}")

        except Exception as exc:
            print(f"Error executing SQLite snapshot: {exc}", file=sys.stderr)
            if temp_target_db.exists():
                temp_target_db.unlink()
            return 1

    # 2. Mirror Receipts
    source_receipts = settings.RECEIPT_STORAGE_DIR
    target_receipts = backup_dir / "receipts"
    target_receipts.mkdir(parents=True, exist_ok=True)

    if source_receipts.exists():
        if sys.platform == "win32":
            # Fast incremental robocopy on Windows
            cmd = [
                "robocopy",
                str(source_receipts),
                str(target_receipts),
                "/MIR",
                "/FFT",
                "/Z",
                "/NP",
                "/NDL",
                "/NJS",
                "/NJH",
            ]
            subprocess.run(cmd, check=False)  # robocopy exit codes < 8 indicate success
        else:
            for item in source_receipts.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(source_receipts)
                    dest = target_receipts / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if not dest.exists() or dest.stat().st_mtime < item.stat().st_mtime:
                        shutil.copy2(item, dest)

        print(f"Receipts mirrored to: {target_receipts}")

    return 0


if __name__ == "__main__":
    sys.exit(run_backup())
