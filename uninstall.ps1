<#
.SYNOPSIS
    Uninstaller for Commit (commit-ai) on Windows.
.DESCRIPTION
    Removes Commit's isolated virtual environment and command launcher.
    Does NOT remove unrelated Python packages or user data.
#>
[CmdletBinding()]
param ()

$ErrorActionPreference = "Stop"

$PackageName = "commit-ai"
$AppDataDir = Join-Path $env:LOCALAPPDATA "commit-ai"
$VenvDir = Join-Path $AppDataDir "venv"
$BinDir = Join-Path $AppDataDir "bin"
$LauncherPath = Join-Path $BinDir "commit.cmd"

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host " Commit ($PackageName) Windows Uninstaller" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan

$removedAny = $false

if (Test-Path $LauncherPath) {
    Write-Host "Removing launcher: $LauncherPath"
    Remove-Item -Force $LauncherPath
    $removedAny = $true
}

if (Test-Path $VenvDir) {
    Write-Host "Removing isolated environment: $VenvDir"
    Remove-Item -Recurse -Force $VenvDir
    $removedAny = $true
}

if ((Test-Path $BinDir) -and ((Get-ChildItem $BinDir | Measure-Object).Count -eq 0)) {
    Remove-Item -Force $BinDir
}

if ((Test-Path $AppDataDir) -and ((Get-ChildItem $AppDataDir | Measure-Object).Count -eq 0)) {
    Remove-Item -Force $AppDataDir
}

Write-Host ""
if ($removedAny) {
    Write-Host "✓ Commit ($PackageName) has been successfully uninstalled." -ForegroundColor Green
} else {
    Write-Host "No active Commit installation found in $AppDataDir." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Note: Configuration (%APPDATA%\commit) and history (%LOCALAPPDATA%\commit) were preserved."
Write-Host "To remove configuration and history data as well, run in PowerShell:"
Write-Host '  Remove-Item -Recurse -Force "$env:APPDATA\commit", "$env:LOCALAPPDATA\commit"'
Write-Host "=======================================================" -ForegroundColor Cyan
exit 0
