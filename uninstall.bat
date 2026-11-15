@echo off
rem ============================================================================
rem Commit (commit-ai) — Windows Uninstaller Launcher
rem ============================================================================
rem Delegates directly to uninstall.ps1 using a process-scoped execution policy override.
rem ============================================================================

setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
