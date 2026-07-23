@echo off
REM Starts both the Flask backend (port 5001) and the Next.js frontend
REM (port 3000) in their own windows, so you can see each one's logs
REM separately and tell immediately if either one fails to start.
REM
REM If localhost gives a 404: you were almost certainly only seeing the
REM backend's logs (port 5001 has no "/" route — Flask 404s there on
REM purpose). The actual site is the frontend, at http://localhost:3000.

echo Starting Xoltra backend (Flask, port 5001)...
start "Xoltra Backend" cmd /k "cd /d %~dp0backend && python app.py"

echo Starting Xoltra frontend (Next.js, port 3000)...
start "Xoltra Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Both services are starting in separate windows.
echo   Backend:  http://localhost:5001  (API only - no page here, 404 on "/" is expected)
echo   Frontend: http://localhost:3000  (open THIS one in your browser)
echo.
echo First run only: if the frontend window shows "Cannot find module" or
echo similar, close it and run install.bat first, then dev.bat again.
