@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Remove-B360GT-From-Path.ps1"
set "B360GT_EXIT_CODE=%ERRORLEVEL%"
echo.
pause
exit /b %B360GT_EXIT_CODE%
