@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Add-B360GT-To-Path.ps1"
set "B360GT_EXIT_CODE=%ERRORLEVEL%"
echo.
pause
exit /b %B360GT_EXIT_CODE%
