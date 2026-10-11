@echo off
REM Start Healthies at http://localhost:8000  (Windows)
cd /d %~dp0
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10+ from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -q -r backend\requirements-dev.txt
if not exist frontend\dist\index.html goto build
goto start
:build
echo Building the frontend - needs Node.js 18 or newer...
pushd frontend
call npm install
call npm run build
popd
:start
cd backend
if "%HEALTHIES_MODEL_BACKEND%"=="" set HEALTHIES_MODEL_BACKEND=fixture
echo.
echo Healthies is running. Open http://localhost:8000 in your browser. Press Ctrl+C to stop.
echo.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
