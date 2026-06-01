from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

RUBRIC_COLUMNS = [
    "clinical_relevance_score",
    "question_specificity_score",
    "safety_score",
    "linguistic_score",
    "denial_handling_score",
    "department_accuracy_score",
]

BASE_DIR = Path(__file__).resolve().parent
EVAL_DB_PATH = BASE_DIR / "data" / "expert_evaluations.sqlite"


def database_backend() -> str:
    return "postgresql" if os.getenv("DATABASE_URL", "").strip() else "sqlite"


def _postgres_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


@contextmanager
def db_conn() -> Iterator[Any]:
    if database_backend() == "postgresql":
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(_postgres_url(), row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        EVAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(EVAL_DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _ph(conn: Any) -> str:
    return "%s" if database_backend() == "postgresql" else "?"


def _in_clause(conn: Any, n: int) -> str:
    ph = _ph(conn)
    return ", ".join([ph] * n)


def ensure_tables() -> None:
    with db_conn() as conn:
        if database_backend() == "postgresql":
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expert_evaluations (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER NOT NULL UNIQUE,
                    department_name VARCHAR(100) NOT NULL,
                    clinical_relevance_score INTEGER,
                    question_specificity_score INTEGER,
                    safety_score INTEGER,
                    linguistic_score INTEGER,
                    denial_handling_score INTEGER,
                    department_accuracy_score INTEGER,
                    doctor_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_expert_evaluations_session
                ON expert_evaluations(session_id)
                """
            )
        else:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expert_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL UNIQUE,
                    department_name VARCHAR(100) NOT NULL,
                    clinical_relevance_score INTEGER,
                    question_specificity_score INTEGER,
                    safety_score INTEGER,
                    linguistic_score INTEGER,
                    denial_handling_score INTEGER,
                    department_accuracy_score INTEGER,
                    doctor_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_expert_evaluations_session ON expert_evaluations(session_id)"
            )


def row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def is_evaluation_complete(row: Any | None) -> bool:
    if row is None:
        return False
    data = row_to_dict(row)
    for col in RUBRIC_COLUMNS:
        val = data.get(col)
        if val is None or val == "":
            return False
    return True


def evaluation_status(row: Any | None) -> str:
    if row is None:
        return "pending"
    if is_evaluation_complete(row):
        return "complete"
    return "incomplete"


def fetch_evaluations(conn: Any, session_ids: list[int]) -> dict[int, Any]:
    if not session_ids:
        return {}
    ph = _in_clause(conn, len(session_ids))
    cur = conn.execute(
        f"SELECT * FROM expert_evaluations WHERE session_id IN ({ph})",
        session_ids,
    )
    rows = cur.fetchall()
    return {int(row_to_dict(r)["session_id"]): r for r in rows}


def fetch_evaluation(conn: Any, session_id: int) -> Any | None:
    ph = _ph(conn)
    cur = conn.execute(
        f"SELECT * FROM expert_evaluations WHERE session_id = {ph}",
        (session_id,),
    )
    return cur.fetchone()


def save_evaluation(
    conn: Any,
    session_id: int,
    department_name: str,
    data: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    existing = fetch_evaluation(conn, session_id)
    ph = _ph(conn)
    if existing:
        set_part = ", ".join([f"{c} = {ph}" for c in RUBRIC_COLUMNS])
        params = [data[c] for c in RUBRIC_COLUMNS] + [
            data.get("doctor_notes"),
            now,
            department_name,
            session_id,
        ]
        conn.execute(
            f"UPDATE expert_evaluations SET {set_part}, doctor_notes = {ph}, updated_at = {ph}, department_name = {ph} WHERE session_id = {ph}",
            params,
        )
    else:
        cols = ["session_id", "department_name", *RUBRIC_COLUMNS, "doctor_notes", "created_at", "updated_at"]
        vals = [
            session_id,
            department_name,
            *[data[c] for c in RUBRIC_COLUMNS],
            data.get("doctor_notes"),
            now,
            now,
        ]
        placeholders = ", ".join([ph] * len(cols))
        conn.execute(
            f"INSERT INTO expert_evaluations ({','.join(cols)}) VALUES ({placeholders})",
            vals,
        )
    return row_to_dict(fetch_evaluation(conn, session_id))


def delete_evaluation(conn: Any, session_id: int) -> int:
    ph = _ph(conn)
    cur = conn.execute(
        f"DELETE FROM expert_evaluations WHERE session_id = {ph}",
        (session_id,),
    )
    return int(getattr(cur, "rowcount", 0) or 0)


def delete_all_evaluations(conn: Any) -> int:
    cur = conn.execute("SELECT COUNT(*) AS n FROM expert_evaluations")
    row = cur.fetchone()
    n = int(row_to_dict(row).get("n") or row[0] if row else 0)
    conn.execute("DELETE FROM expert_evaluations")
    return n


def storage_info() -> str:
    if database_backend() == "postgresql":
        return "postgresql (DATABASE_URL)"
    return str(EVAL_DB_PATH)
