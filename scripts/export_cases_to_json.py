"""One-time export: hospital.db -> data/expert_cases.json"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import EXPERT_DEPARTMENTS, session_ids_for_department  # noqa: E402

DB = ROOT / "hospital.db"
OUT = ROOT / "data" / "expert_cases.json"


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"Missing {DB}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    all_session_ids: list[int] = []
    for dept in EXPERT_DEPARTMENTS:
        all_session_ids.extend(session_ids_for_department(dept))

    placeholders = ",".join(["?"] * len(all_session_ids))
    rows = conn.execute(
        f"""
        SELECT id, session_id, role, content, created_at
        FROM chat_messages
        WHERE session_id IN ({placeholders})
          AND role IN ('user', 'assistant')
        ORDER BY session_id ASC, created_at ASC
        """,
        all_session_ids,
    ).fetchall()
    conn.close()

    by_session: dict[str, list[dict]] = {}
    for r in rows:
        sid = str(int(r["session_id"]))
        by_session.setdefault(sid, []).append(
            {
                "id": int(r["id"]),
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"],
            }
        )

    departments: dict[str, list[int]] = {}
    for dept in EXPERT_DEPARTMENTS:
        ids = session_ids_for_department(dept)
        active = [sid for sid in ids if str(sid) in by_session]
        departments[dept.id] = active

    payload = {
        "version": 1,
        "departments": departments,
        "messages_by_session": by_session,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    total_sessions = len(by_session)
    total_msgs = sum(len(v) for v in by_session.values())
    print(f"Wrote {OUT} ({total_sessions} sessions, {total_msgs} messages)")


if __name__ == "__main__":
    main()
