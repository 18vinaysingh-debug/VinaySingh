@echo off
REM Runs today's pipeline, then opens the dashboard. Also used by Windows Task Scheduler.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
if not exist logs mkdir logs
python run.py daily >> logs\daily.log 2>&1
python run.py dashboard >nul
start "" "reports\dashboard.html"
