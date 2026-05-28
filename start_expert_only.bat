@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt

if "%EXPERT_DB_PATH%"=="" (
  set "EXPERT_DB_PATH=%~dp0hospital.db"
)

echo.
echo Expert standalone running on http://127.0.0.1:8010/expert
python -m uvicorn app:app --host 127.0.0.1 --port 8010
