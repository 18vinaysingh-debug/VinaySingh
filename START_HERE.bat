@echo off
REM One-time setup on Windows. Double-click this file.
cd /d "%~dp0"
where python >nul 2>nul || (echo Python not found. Install Python 3.11+ from python.org and tick "Add to PATH". & pause & exit /b)
where ffmpeg >nul 2>nul || (echo Installing ffmpeg... & winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if not exist .env copy .env.example .env >nul
echo.
echo ============================================================
echo  Setup done. Now open the file ".env" in Notepad and paste
echo  your GEMINI_API_KEY (and PEXELS_API_KEY), then double-click
echo  RUN_DAILY.bat.   If ffmpeg was just installed, close and
echo  reopen this window first.
echo ============================================================
python run.py check
pause
