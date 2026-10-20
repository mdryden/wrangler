"""Checks whether pending Alembic migrations exist.

Exit Codes:
  0: Database schema is fully up-to-date.
  2: Pending migrations detected.
  1: Error inspecting database or alembic environment.
"""

import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from database import engine


def check_migrations() -> int:
    try:
        ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
        alembic_cfg = Config(str(ini_path))
        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()

        with engine.connect() as conn:
            inspector = inspect(conn)
            if "alembic_version" not in inspector.get_table_names():
                # No migration table exists yet
                print("No alembic_version table found. Migrations pending.")
                return 2

            result = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            row = result.fetchone()
            current_rev = row[0] if row else None

        if current_rev != head_rev:
            print(f"Pending migrations: current={current_rev}, head={head_rev}")
            return 2

        print(f"Database up-to-date at revision {current_rev}")
        return 0

    except Exception as exc:
        print(f"Error checking migration status: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(check_migrations())
