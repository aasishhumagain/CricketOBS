@echo off
cd /d "%~dp0"
python --version
if errorlevel 1 goto fail
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if not exist ".venv\Scripts\python.exe" goto fail
".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
  python -m pip --python .venv install -r requirements.txt
) else (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
if errorlevel 1 goto fail
echo Setup complete. Run run.bat next.
pause
exit /b 0
:fail
echo Setup failed. Install Python 3.11 or newer with Python added to PATH, then retry.
pause
exit /b 1
