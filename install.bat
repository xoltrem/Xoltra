@echo off
REM One-time setup. Run this once (and again any time requirements.txt or
REM package.json change), then use dev.bat every time after that.

echo Installing backend (Python) dependencies...
cd /d %~dp0backend
pip install -r requirements.txt
cd /d %~dp0

echo.
echo Installing frontend (Node) dependencies...
cd /d %~dp0frontend
npm install
cd /d %~dp0

echo.
echo Done. Copy backend\.env.example to backend\.env (and frontend\.env.example
echo to frontend\.env.local if present) and fill in real values before running
echo dev.bat.
pause
