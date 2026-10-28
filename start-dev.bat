@echo off
setlocal
set "ROOT=%~dp0"
where pwsh.exe >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start_dev.ps1" %*
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start_dev.ps1" %*
)
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%~1"=="" exit /b %EXITCODE%
pause
exit /b %EXITCODE%
