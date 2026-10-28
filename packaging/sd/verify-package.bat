@echo off
setlocal
where pwsh.exe >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_package.ps1"
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_package.ps1"
)
set "EXITCODE=%ERRORLEVEL%"
echo.
pause
exit /b %EXITCODE%
