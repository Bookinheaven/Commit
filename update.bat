@echo off
rem ============================================================================
rem Commit (commit-ai) — Windows Quick Updater Entry Point
rem ============================================================================
rem Pulls latest Git changes and updates Commit in-place.
rem ============================================================================

setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
