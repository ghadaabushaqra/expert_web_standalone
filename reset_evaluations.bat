@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run start_expert_only.bat once to create .venv first.
  exit /b 1
)
".venv\Scripts\python.exe" scripts\reset_evaluations.py
pause
