@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

if not exist "logs" mkdir "logs"

for /f %%a in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%a"
set "LOGFILE=logs\run_%TODAY%.log"

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
) else if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

echo ==== run_weekly.bat started %date% %time% ==== >> "%LOGFILE%"
python -m scripts.run_weekly >> "%LOGFILE%" 2>&1
set "EXITCODE=%ERRORLEVEL%"
echo ==== run_weekly.bat finished %date% %time% (exit code %EXITCODE%) ==== >> "%LOGFILE%"

endlocal & exit /b %EXITCODE%
