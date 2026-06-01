# Expert Website Standalone

This folder is fully dedicated to the expert evaluation website (`/expert`) and separated from the main system runtime.

## Included files

- `app.py` standalone FastAPI backend
- `data/expert_cases.json` embedded case conversations (no `hospital.db` required to run)
- `frontend/expert/*.html` expert pages
- `frontend/static/expert.js` frontend logic
- `frontend/static/expert.css` styles
- `requirements.txt`
- `start_expert_only.bat`
- `scripts/export_cases_to_json.py` re-export cases from `hospital.db` if needed

## Run locally

1. Start:
   - Run `start_expert_only.bat`
2. Open:
   - `http://127.0.0.1:8010/expert`

Doctor evaluations are saved locally in `data/expert_evaluations.sqlite` (created automatically; not committed to git).

## Deploy on Render (persistent evaluations)

On Render, files inside the web service are **temporary** — SQLite evaluations can disappear after redeploy or restart.

**Use Render PostgreSQL** so doctor evaluations are saved permanently.

### Step-by-step on Render

1. **Dashboard** → **New +** → **PostgreSQL**
2. Name: e.g. `expert-evaluations` → **Create Database**
3. Open your **Web Service** (the expert site)
4. **Environment** → **Add from Database** → select the PostgreSQL you created
5. Render adds `DATABASE_URL` automatically — the app uses it on startup
6. **Manual Deploy** → **Deploy latest commit**
7. Check: open `https://YOUR-APP.onrender.com/health`  
   - `"database_backend": "postgresql"` = evaluations are persistent

### Web service settings

- **Build:** `pip install -r requirements.txt`
- **Start:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
- **Python:** `3.11.9` (`.python-version` or `PYTHON_VERSION`)

Locally (without `DATABASE_URL`) evaluations still use `data/expert_evaluations.sqlite`.

1. Push this repo to GitHub (cases are already in `data/expert_cases.json`).
2. Deploy on a server that runs FastAPI/uvicorn (Render, Railway, VPS, etc.).
3. Point your domain to that server.
4. Share `https://your-domain.com/expert` with doctors.

You do **not** need to upload `hospital.db` to GitHub or the server for cases to appear.

## Refresh cases from hospital.db (optional, dev only)

If conversations change in the main database:

1. Place `hospital.db` in this folder (or use `copy_database_here.bat`).
2. Run: `python scripts/export_cases_to_json.py`
3. Commit the updated `data/expert_cases.json`.
