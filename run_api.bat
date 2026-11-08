@echo off
REM Start SpendGuard on http://127.0.0.1:8000  (API docs: http://127.0.0.1:8000/docs)
REM Installs any new packages first, so a fresh pull always runs.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment in .venv ...
  python -m venv .venv || goto :fail
)
echo Checking packages ...
".venv\Scripts\python.exe" -m pip install -q -r backend\requirements.txt || goto :fail
cd backend
"..\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
goto :eof
:fail
echo.
echo Something failed above. Copy the red lines and send them to Claude.
