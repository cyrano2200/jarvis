@echo off
setlocal
cd /d "%~dp0"
echo ==== Jarvis setup (Windows) ====
where python >nul 2>nul || (echo Python 3.10+ not found. Install from https://www.python.org/downloads/ and tick "Add to PATH". & pause & exit /b 1)
if not exist venv (
  echo Creating virtual environment...
  python -m venv venv || (echo Failed to create venv & pause & exit /b 1)
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Some packages failed. If PyAudio failed, try:  pip install pipwin ^&^& pipwin install pyaudio
  echo Continuing anyway - Jarvis still runs in typed mode ^(--text^).
)
if not exist .env copy .env.example .env >nul

REM ---- launcher scripts ----
> run_jarvis.bat echo @echo off
>> run_jarvis.bat echo cd /d "%%~dp0"
>> run_jarvis.bat echo call venv\Scripts\activate.bat
>> run_jarvis.bat echo python jarvis.py %%*
> run_jarvis_background.vbs echo CreateObject("Wscript.Shell").Run """%~dp0venv\Scripts\pythonw.exe"" ""%~dp0jarvis.py"" --tray", 0, False

REM ---- desktop shortcut ----
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Jarvis.lnk'); $s.TargetPath='%~dp0run_jarvis_background.vbs'; $s.WorkingDirectory='%~dp0'; $s.Description='Jarvis assistant (tray)'; $s.Save()"

echo.
echo Setup complete.
echo   Test:        python jarvis.py --check
echo   Run:         run_jarvis.bat            (console)   or   double-click the "Jarvis" desktop shortcut (tray)
echo   Auto-start:  press Win+R, type shell:startup, and drop a copy of the Jarvis shortcut there.
pause
