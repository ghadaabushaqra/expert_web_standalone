"""Delete all saved doctor evaluations so every case shows as not evaluated."""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "expert_evaluations.sqlite"
EXPORT_DIR = ROOT / "data" / "exports"


def main() -> None:
    if DB.exists():
        conn = sqlite3.connect(DB)
        try:
            n = conn.execute("SELECT COUNT(*) FROM expert_evaluations").fetchone()[0]
            conn.execute("DELETE FROM expert_evaluations")
            conn.commit()
            print(f"Deleted {n} evaluation(s) from {DB}")
        finally:
            conn.close()
    else:
        print(f"No database at {DB} (nothing to delete)")

    if EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)
        print(f"Removed {EXPORT_DIR}")
    print("All cases will show as not evaluated.")


if __name__ == "__main__":
    main()
    sys.exit(0)
