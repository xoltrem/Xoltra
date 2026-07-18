@echo off
REM Closes the backend/frontend windows dev.bat opened.

taskkill /FI "WINDOWTITLE eq Xoltra Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Xoltra Frontend*" /T /F >nul 2>&1

echo Stopped Xoltra backend and frontend (if they were running).
