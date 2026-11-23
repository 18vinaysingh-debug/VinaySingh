@echo off
REM Opens a command window inside the project with everything activated.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python run.py status
echo.
echo Examples:
echo   python run.py approve CONTENT-2026-001
echo   python run.py revise  CONTENT-2026-001 "hook ko aur strong karo"
echo   python run.py reject  CONTENT-2026-001 "topic weak"
echo   python run.py mark-ig CONTENT-2026-001 https://www.instagram.com/reel/XXXX/
echo.
cmd /k
