@echo off
cd /d %~dp0
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Backend venv missing: .venv\Scripts\python.exe
  pause
  exit /b 1
)
if not exist "ai_server\.venv\Scripts\python.exe" (
  echo [ERROR] AI venv missing: ai_server\.venv\Scripts\python.exe
  pause
  exit /b 1
)
if not exist ".env" (
  echo [ERROR] Backend .env missing. Copy .env.example and edit it.
  pause
  exit /b 1
)
if not exist "ai_server\.env" (
  echo [ERROR] AI .env missing. Copy ai_server\.env.example and edit it.
  pause
  exit /b 1
)
start "SCOPE AI 8100" cmd /k "cd /d %~dp0ai_server && call run.bat"
call start_integrated.bat
