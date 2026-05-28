@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Expert standalone running on http://127.0.0.1:8010/expert
echo Cases loaded from data\expert_cases.json
python -m uvicorn app:app --host 127.0.0.1 --port 8010
