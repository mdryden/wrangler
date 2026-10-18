import sqlite3
from pathlib import Path


def clear_staged_transactions() -> None:
    db_path = Path(__file__).resolve().parent.parent / "wrangler.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")
    cur.execute("DELETE FROM staged_allocations;")
    alloc_count = cur.rowcount
    cur.execute("DELETE FROM staged_transactions;")
    tx_count = cur.rowcount
    conn.commit()
    conn.close()
    print(f"Successfully dropped {tx_count} staged transactions and {alloc_count} staged allocations from {db_path.name}.")


if __name__ == "__main__":
    clear_staged_transactions()
