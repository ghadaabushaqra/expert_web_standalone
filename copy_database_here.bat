@echo off
setlocal
cd /d "%~dp0"

if exist "hospital.db" (
  echo hospital.db already exists in expert_web_standalone.
  exit /b 0
)

copy "..\hospital.db" "hospital.db"
echo Copied hospital.db to expert_web_standalone.
