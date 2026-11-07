@echo off
REM Start the SpendGuard API on http://127.0.0.1:8000  (API docs: http://127.0.0.1:8000/docs)
cd /d "%~dp0backend"
"..\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
