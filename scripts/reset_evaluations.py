"""Local dev only: clear all evaluations (SQLite or DATABASE_URL). Not exposed on the website."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db_store import db_conn, delete_all_evaluations, database_backend  # noqa: E402

EXPORT_DIR = ROOT / "data" / "exports"


def main() -> None:
    with db_conn() as conn:
        n = delete_all_evaluations(conn)
    print(f"Deleted {n} evaluation(s) via {database_backend()}")
    if EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)
        print(f"Removed {EXPORT_DIR}")
    print("All cases will show as not evaluated.")


if __name__ == "__main__":
    main()
    sys.exit(0)
