@echo off
rem PC-to-TV casting GUI launcher (ASCII only on purpose)
setlocal
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw run_gui.py
) else (
    py run_gui.py
    if errorlevel 1 pause
)
endlocal