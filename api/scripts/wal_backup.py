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
