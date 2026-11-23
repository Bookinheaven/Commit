<#
.SYNOPSIS
    Quick updater script for Commit (commit-ai) on Windows.
.DESCRIPTION
    Pulls the latest commits from the Git repository and updates the isolated
    Commit environment under %LOCALAPPDATA%\commit-ai\venv.
#>
[CmdletBinding()]
param (
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
Set-Location $ScriptDir

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host " Commit Windows Updater" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan

# If inside a git repository, pull latest changes
try {
    $isGit = & git rev-parse --is-inside-work-tree 2>$null
    if ($LASTEXITCODE -eq 0 -and $isGit -eq "true") {
        Write-Host "==> Pulling latest changes from Git repository..." -ForegroundColor Yellow
        & git pull --ff-only
    }
} catch {
    Write-Host "Notice: Git pull skipped or not in git repository." -ForegroundColor DarkGray
}

& "$ScriptDir\install.ps1"
