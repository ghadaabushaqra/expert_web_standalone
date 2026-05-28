# Expert Website Standalone

This folder is fully dedicated to the expert evaluation website (`/expert`) and separated from the main system runtime.

## Included files

- `app.py` standalone FastAPI backend
- `frontend/expert/*.html` expert pages
- `frontend/static/expert.js` frontend logic
- `frontend/static/expert.css` styles
- `requirements.txt`
- `start_expert_only.bat`
- `copy_database_here.bat`

## Run locally

1. Optional: copy database into this folder:
   - Run `copy_database_here.bat`
2. Start:
   - Run `start_expert_only.bat`
3. Open:
   - `http://127.0.0.1:8010/expert`

## Database path

- By default, `start_expert_only.bat` uses `expert_web_standalone/hospital.db`.
- You can point to another DB with:
  - `set EXPERT_DB_PATH=C:\path\to\hospital.db`
  - then run `start_expert_only.bat`.
