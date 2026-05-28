from __future__ import annotations

import csv
import io
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
EXPERT_FRONTEND_DIR = FRONTEND_DIR / "expert"
STATIC_DIR = FRONTEND_DIR / "static"
CASES_PATH = BASE_DIR / "data" / "expert_cases.json"
EVAL_DB_PATH = BASE_DIR / "data" / "expert_evaluations.sqlite"

_cases_data: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExpertDepartment:
    id: str
    name_ar: str
    icon: str
    session_min: int
    session_max: int
    exclude_session_ids: frozenset[int]


EXPERT_DEPARTMENTS = [
    ExpertDepartment("neurology", "طب الأعصاب", "🧠", 280, 299, frozenset()),
    ExpertDepartment("ophthalmology", "طب العيون", "👁️", 300, 319, frozenset()),
    ExpertDepartment("ent", "الأنف والأذن والحنجرة", "👂", 320, 339, frozenset()),
    ExpertDepartment("gi", "أمراض الجهاز الهضمي", "🍽️", 340, 361, frozenset({355})),
    ExpertDepartment("chest", "أمراض الصدر", "🫁", 362, 382, frozenset({366})),
]

RUBRIC_COLUMNS = [
    "clinical_relevance_score",
    "question_specificity_score",
    "single_question_score",
    "safety_score",
    "linguistic_score",
    "denial_handling_score",
    "department_accuracy_score",
    "clinical_reasoning_score",
]


class ExpertEvaluationSave(BaseModel):
    clinical_relevance_score: int = Field(ge=1, le=3)
    question_specificity_score: int = Field(ge=1, le=3)
    single_question_score: int = Field(ge=1, le=3)
    safety_score: int = Field(ge=1, le=3)
    linguistic_score: int = Field(ge=1, le=3)
    denial_handling_score: int = Field(ge=1, le=3)
    department_accuracy_score: int = Field(ge=1, le=3)
    clinical_reasoning_score: int = Field(ge=1, le=3)
    doctor_notes: str | None = None


def get_department(dept_id: str) -> ExpertDepartment | None:
    for dept in EXPERT_DEPARTMENTS:
        if dept.id == dept_id:
            return dept
    return None


def session_ids_for_department(dept: ExpertDepartment) -> list[int]:
    return [
        sid
        for sid in range(dept.session_min, dept.session_max + 1)
        if sid not in dept.exclude_session_ids
    ]


def load_cases() -> dict[str, Any]:
    global _cases_data
    if _cases_data is not None:
        return _cases_data
    if not CASES_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Cases data not found: {CASES_PATH}. Run scripts/export_cases_to_json.py if needed.",
        )
    _cases_data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return _cases_data


def session_has_messages(session_id: int) -> bool:
    cases = load_cases()
    return str(session_id) in cases.get("messages_by_session", {})


def get_conn() -> sqlite3.Connection:
    EVAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(EVAL_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables() -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expert_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL UNIQUE,
                department_name VARCHAR(100) NOT NULL,
                clinical_relevance_score INTEGER,
                question_specificity_score INTEGER,
                single_question_score INTEGER,
                safety_score INTEGER,
                linguistic_score INTEGER,
                denial_handling_score INTEGER,
                department_accuracy_score INTEGER,
                clinical_reasoning_score INTEGER,
                doctor_notes TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_expert_evaluations_session ON expert_evaluations(session_id)"
        )
        conn.commit()
    finally:
        conn.close()


def department_active_ids(dept_id: str) -> tuple[ExpertDepartment, list[int]]:
    dept = get_department(dept_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="القسم غير موجود")
    cases = load_cases()
    active = [int(sid) for sid in cases.get("departments", {}).get(dept_id, [])]
    if not active:
        ids = session_ids_for_department(dept)
        active = [sid for sid in ids if session_has_messages(sid)]
    return dept, active


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def evaluated_session_ids(conn: sqlite3.Connection, active: list[int]) -> set[int]:
    if not active:
        return set()
    placeholders = ",".join(["?"] * len(active))
    rows = conn.execute(
        f"SELECT session_id FROM expert_evaluations WHERE session_id IN ({placeholders})",
        active,
    ).fetchall()
    return {int(r["session_id"]) for r in rows}


app = FastAPI(title="Expert Evaluation Standalone")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def startup() -> None:
    load_cases()
    ensure_tables()


@app.get("/health")
def health() -> dict[str, str]:
    cases = load_cases()
    session_count = len(cases.get("messages_by_session", {}))
    return {
        "status": "ok",
        "cases_source": str(CASES_PATH),
        "case_sessions": str(session_count),
        "evaluations_db": str(EVAL_DB_PATH),
    }


@app.get("/", response_class=HTMLResponse)
def root() -> RedirectResponse:
    return RedirectResponse("/expert", status_code=302)


def serve_html(name: str) -> HTMLResponse:
    p = EXPERT_FRONTEND_DIR / name
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Missing page: {name}")
    return HTMLResponse(p.read_text(encoding="utf-8"))


@app.get("/expert", response_class=HTMLResponse)
def expert_index() -> HTMLResponse:
    return serve_html("index.html")


@app.get("/expert/department", response_class=HTMLResponse)
def expert_department() -> HTMLResponse:
    return serve_html("department.html")


@app.get("/expert/case", response_class=HTMLResponse)
def expert_case() -> HTMLResponse:
    return serve_html("case.html")


@app.get("/api/expert/departments")
def api_departments() -> list[dict[str, Any]]:
    load_cases()
    out = []
    for dept in EXPERT_DEPARTMENTS:
        _, active = department_active_ids(dept.id)
        out.append(
            {
                "id": dept.id,
                "name_ar": dept.name_ar,
                "icon": dept.icon,
                "case_count": len(active),
            }
        )
    return out


@app.get("/api/expert/departments/{dept_id}/summary")
def api_summary(dept_id: str) -> dict[str, Any]:
    conn = get_conn()
    try:
        dept, active = department_active_ids(dept_id)
        evaluated = evaluated_session_ids(conn, active)
        total = len(active)
        done = len(evaluated)
        return {
            "dept_id": dept.id,
            "department_name": dept.name_ar,
            "total_cases": total,
            "evaluated_count": done,
            "pending_count": max(0, total - done),
            "all_evaluated": total > 0 and done == total,
            "csv_download_url": f"/api/expert/departments/{dept_id}/evaluations.csv",
        }
    finally:
        conn.close()


@app.get("/api/expert/departments/{dept_id}/cases")
def api_cases(dept_id: str) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        _, active = department_active_ids(dept_id)
        evaluated = evaluated_session_ids(conn, active)
        return [
            {"case_number": i + 1, "session_id": sid, "evaluated": sid in evaluated}
            for i, sid in enumerate(active)
        ]
    finally:
        conn.close()


@app.get("/api/expert/departments/{dept_id}/evaluations.csv")
def api_csv(dept_id: str) -> Response:
    conn = get_conn()
    try:
        dept, active = department_active_ids(dept_id)
        if not active:
            raise HTTPException(status_code=404, detail="لا توجد حالات في هذا القسم")
        placeholders = ",".join(["?"] * len(active))
        rows = conn.execute(
            f"SELECT * FROM expert_evaluations WHERE session_id IN ({placeholders})",
            active,
        ).fetchall()
        by_sid = {int(r["session_id"]): row_to_dict(r) for r in rows}
        cols = [
            "case_number",
            "session_id",
            "department_name",
            "evaluated",
            *RUBRIC_COLUMNS,
            "doctor_notes",
            "created_at",
            "updated_at",
        ]
        buf = io.StringIO()
        buf.write("\ufeff")
        writer = csv.DictWriter(buf, fieldnames=cols)
        writer.writeheader()
        for i, sid in enumerate(active, start=1):
            ev = by_sid.get(sid)
            writer.writerow(
                {
                    "case_number": i,
                    "session_id": sid,
                    "department_name": dept.name_ar,
                    "evaluated": "yes" if ev else "no",
                    **{k: ev.get(k, "") if ev else "" for k in RUBRIC_COLUMNS},
                    "doctor_notes": ev.get("doctor_notes", "") if ev else "",
                    "created_at": ev.get("created_at", "") if ev else "",
                    "updated_at": ev.get("updated_at", "") if ev else "",
                }
            )
        filename = f"expert_evaluations_{dept_id}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
        return Response(
            content=buf.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        conn.close()


@app.get("/api/expert/sessions/{session_id}/messages")
def api_messages(session_id: int, dept_id: str) -> list[dict[str, Any]]:
    _, active = department_active_ids(dept_id)
    if session_id not in active:
        raise HTTPException(status_code=404, detail="الجلسة غير ضمن هذا القسم")
    cases = load_cases()
    rows = cases.get("messages_by_session", {}).get(str(session_id), [])
    if not rows:
        raise HTTPException(status_code=404, detail="لا توجد رسائل لهذه الجلسة")
    return rows


@app.get("/api/expert/sessions/{session_id}/evaluation")
def api_get_eval(session_id: int, dept_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    try:
        _, active = department_active_ids(dept_id)
        if session_id not in active:
            raise HTTPException(status_code=404, detail="الجلسة غير ضمن هذا القسم")
        row = conn.execute(
            "SELECT * FROM expert_evaluations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


@app.put("/api/expert/sessions/{session_id}/evaluation")
def api_save_eval(session_id: int, dept_id: str, body: ExpertEvaluationSave) -> dict[str, Any]:
    conn = get_conn()
    try:
        dept, active = department_active_ids(dept_id)
        if session_id not in active:
            raise HTTPException(status_code=404, detail="الجلسة غير ضمن هذا القسم")
        if not session_has_messages(session_id):
            raise HTTPException(status_code=404, detail="لا توجد رسائل لهذه الجلسة")
        data = body.model_dump()
        now = datetime.utcnow().isoformat()
        row = conn.execute(
            "SELECT id FROM expert_evaluations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row:
            set_part = ", ".join([f"{c} = ?" for c in RUBRIC_COLUMNS]) + ", doctor_notes = ?, updated_at = ?, department_name = ?"
            params = [data[c] for c in RUBRIC_COLUMNS] + [data.get("doctor_notes"), now, dept.name_ar, session_id]
            conn.execute(f"UPDATE expert_evaluations SET {set_part} WHERE session_id = ?", params)
        else:
            cols = ["session_id", "department_name", *RUBRIC_COLUMNS, "doctor_notes", "created_at", "updated_at"]
            vals = [session_id, dept.name_ar, *[data[c] for c in RUBRIC_COLUMNS], data.get("doctor_notes"), now, now]
            placeholders = ",".join(["?"] * len(cols))
            conn.execute(
                f"INSERT INTO expert_evaluations ({','.join(cols)}) VALUES ({placeholders})",
                vals,
            )
        conn.commit()
        out = conn.execute(
            "SELECT * FROM expert_evaluations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row_to_dict(out)
    finally:
        conn.close()


@app.get("/api/expert/sessions/{session_id}/navigation")
def api_nav(session_id: int, dept_id: str) -> dict[str, Any]:
    _, active = department_active_ids(dept_id)
    if session_id not in active:
        raise HTTPException(status_code=404, detail="الجلسة غير ضمن هذا القسم")
    idx = active.index(session_id)
    return {
        "dept_id": dept_id,
        "session_id": session_id,
        "previous_session_id": active[idx - 1] if idx > 0 else None,
        "next_session_id": active[idx + 1] if idx < len(active) - 1 else None,
        "case_number": idx + 1,
        "total_cases": len(active),
    }
