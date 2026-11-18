@echo off
rem Market Skew installer for Windows: runs install.ps1 without changing the PC's script policy. Flags pass through (-Yes, -SkipTests, -NoShortcuts, -NoPredictor).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set CODE=%ERRORLEVEL%
echo.
pause
exit /b %CODE%
