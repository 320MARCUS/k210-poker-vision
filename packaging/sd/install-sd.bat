@echo off
setlocal
set "DRIVE=%~1"
where pwsh.exe >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    if "%DRIVE%"=="" (
        pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_sd.ps1"
    ) else (
        pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_sd.ps1" -Drive "%DRIVE%"
    )
) else (
    if "%DRIVE%"=="" (
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_sd.ps1"
    ) else (
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_sd.ps1" -Drive "%DRIVE%"
    )
)
set "EXITCODE=%ERRORLEVEL%"
echo.
pause
exit /b %EXITCODE%
