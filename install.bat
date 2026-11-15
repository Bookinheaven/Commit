@echo off
rem ============================================================================
rem Commit (commit-ai) — Windows CMD Entry Point
rem ============================================================================
rem Delegates directly to install.ps1 using a process-scoped execution policy override.
rem Double-clicking or executing from Command Prompt runs the PowerShell installer.
rem ============================================================================

setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
