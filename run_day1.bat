@echo off
REM SpendGuard Day 1: create a project-only Python (.venv), install packages, run both tests.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment in .venv ...
  python -m venv .venv || goto :fail
)
echo Installing packages into .venv ...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt -r backend\requirements.txt || goto :fail
echo.
echo ===== PAYPAL PAYOUT TEST =====
".venv\Scripts\python.exe" scripts\paypal_payout_test.py
echo.
echo ===== GROQ TOOL TEST =====
".venv\Scripts\python.exe" scripts\groq_tool_test.py
echo.
echo ===== POLICY ENGINE TESTS =====
pushd backend
"..\.venv\Scripts\python.exe" -m pytest -q
popd
goto :eof
:fail
echo.
echo Something failed above. Copy the red lines and send them to Claude.
