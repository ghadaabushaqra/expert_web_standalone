from __future__ import annotations

import csv
import io
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from db_store import (
    RUBRIC_COLUMNS,
    database_backend,
    db_conn,
    ensure_tables,
    evaluation_status,
    fetch_evaluations,
    fetch_evaluation,
    is_evaluation_complete,
    row_to_dict,
    save_evaluation,
    storage_info,
)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
EXPERT_FRONTEND_DIR = FRONTEND_DIR / "expert"
STATIC_DIR = FRONTEND_DIR / "static"
CASES_PATH = BASE_DIR / "data" / "expert_cases.json"
EXPORT_DIR = BASE_DIR / "data" / "exports"

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


class ExpertEvaluationSave(BaseModel):
    clinical_relevance_score: int = Field(ge=1, le=3)
    question_specificity_score: int = Field(ge=1, le=3)
    safety_score: int = Field(ge=1, le=3)
    linguistic_score: int = Field(ge=1, le=3)
    denial_handling_score: int = Field(ge=1, le=3)
    department_accuracy_score: int = Field(ge=1, le=3)
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


def build_csv_content(dept: ExpertDepartment, active: list[int], by_sid: dict[int, dict[str, Any]]) -> str:
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
        complete = ev and is_evaluation_complete(ev)
        writer.writerow(
            {
                "case_number": i,
                "session_id": sid,
                "department_name": dept.name_ar,
                "evaluated": "yes" if complete else "no",
                **{k: ev.get(k, "") if ev else "" for k in RUBRIC_COLUMNS},
                "doctor_notes": ev.get("doctor_notes", "") if ev else "",
                "created_at": ev.get("created_at", "") if ev else "",
                "updated_at": ev.get("updated_at", "") if ev else "",
            }
        )
    return buf.getvalue()


def sync_csv_exports() -> None:
    if database_backend() != "sqlite":
        return
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with db_conn() as conn:
        for dept in EXPERT_DEPARTMENTS:
            _, active = department_active_ids(dept.id)
            if not active:
                continue
            by_row = fetch_evaluations(conn, active)
            by_sid = {sid: row_to_dict(r) for sid, r in by_row.items()}
            content = build_csv_content(dept, active, by_sid)
            path = EXPORT_DIR / f"expert_evaluations_{dept.id}.csv"
            path.write_text(content, encoding="utf-8")
        master_cols_seen: list[dict[str, Any]] = []
        for dept in EXPERT_DEPARTMENTS:
            _, active = department_active_ids(dept.id)
            by_row = fetch_evaluations(conn, active)
            for sid, row in by_row.items():
                if is_evaluation_complete(row):
                    master_cols_seen.append(row_to_dict(row))
        if master_cols_seen:
            cols = [
                "session_id",
                "department_name",
                *RUBRIC_COLUMNS,
                "doctor_notes",
                "created_at",
                "updated_at",
            ]
            buf = io.StringIO()
            buf.write("\ufeff")
            writer = csv.DictWriter(buf, fieldnames=cols)
            writer.writeheader()
            for ev in sorted(master_cols_seen, key=lambda x: int(x["session_id"])):
                writer.writerow({k: ev.get(k, "") for k in cols})
            (EXPORT_DIR / "expert_evaluations_all.csv").write_text(buf.getvalue(), encoding="utf-8")


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
        "evaluations_storage": storage_info(),
        "database_backend": database_backend(),
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
    with db_conn() as conn:
        dept, active = department_active_ids(dept_id)
        by_row = fetch_evaluations(conn, active)
        done = sum(1 for sid in active if is_evaluation_complete(by_row.get(sid)))
        total = len(active)
        return {
            "dept_id": dept.id,
            "department_name": dept.name_ar,
            "total_cases": total,
            "evaluated_count": done,
            "pending_count": max(0, total - done),
            "all_evaluated": total > 0 and done == total,
            "csv_download_url": f"/api/expert/departments/{dept_id}/evaluations.csv",
        }


@app.get("/api/expert/departments/{dept_id}/cases")
def api_cases(dept_id: str) -> list[dict[str, Any]]:
    with db_conn() as conn:
        _, active = department_active_ids(dept_id)
        by_row = fetch_evaluations(conn, active)
        out = []
        for i, sid in enumerate(active):
            row = by_row.get(sid)
            status = evaluation_status(row)
            out.append(
                {
                    "case_number": i + 1,
                    "session_id": sid,
                    "evaluated": status == "complete",
                    "status": status,
                }
            )
        return out


@app.get("/api/expert/departments/{dept_id}/evaluations.csv")
def api_csv(dept_id: str) -> Response:
    with db_conn() as conn:
        dept, active = department_active_ids(dept_id)
        if not active:
            raise HTTPException(status_code=404, detail="لا توجد حالات في هذا القسم")
        by_row = fetch_evaluations(conn, active)
        by_sid = {sid: row_to_dict(r) for sid, r in by_row.items()}
        content = build_csv_content(dept, active, by_sid)
        filename = f"expert_evaluations_{dept_id}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


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
    with db_conn() as conn:
        _, active = department_active_ids(dept_id)
        if session_id not in active:
            raise HTTPException(status_code=404, detail="الجلسة غير ضمن هذا القسم")
        row = fetch_evaluation(conn, session_id)
        return row_to_dict(row) if row else None


@app.put("/api/expert/sessions/{session_id}/evaluation")
def api_save_eval(session_id: int, dept_id: str, body: ExpertEvaluationSave) -> dict[str, Any]:
    with db_conn() as conn:
        dept, active = department_active_ids(dept_id)
        if session_id not in active:
            raise HTTPException(status_code=404, detail="الجلسة غير ضمن هذا القسم")
        if not session_has_messages(session_id):
            raise HTTPException(status_code=404, detail="لا توجد رسائل لهذه الجلسة")
        data = body.model_dump()
        now = datetime.utcnow().isoformat()
        result = save_evaluation(conn, session_id, dept.name_ar, data, now)
    sync_csv_exports()
    return result


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
