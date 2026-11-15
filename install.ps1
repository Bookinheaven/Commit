<#
.SYNOPSIS
    Self-contained Windows installer for Commit (commit-ai).
.DESCRIPTION
    Installs Commit into an isolated virtual environment under %LOCALAPPDATA%\commit-ai
    using Python's built-in 'venv' and 'ensurepip'.
    Does NOT require pipx, uv, conda, or administrator privileges.
.PARAMETER Uninstall
    Removes Commit's isolated environment and command launcher.
.PARAMETER YesPath
    Automatically add Commit's launcher directory to the User PATH if not present.
.PARAMETER NoPath
    Do not modify the User PATH environment variable.
#>
[CmdletBinding()]
param (
    [switch]$Uninstall,
    [switch]$YesPath,
    [switch]$NoPath,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

$MinPyMajor = 3
$MinPyMinor = 10
$PackageName = "commit-ai"
$CommandName = "commit"

$AppDataDir = Join-Path $env:LOCALAPPDATA "commit-ai"
$VenvDir = Join-Path $AppDataDir "venv"
$BinDir = Join-Path $AppDataDir "bin"
$LauncherPath = Join-Path $BinDir "commit.cmd"

# ------------------------------------------------------------------------------
# 1. Action: Uninstall Handler
# ------------------------------------------------------------------------------
if ($Uninstall) {
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

    # Clean up bin folder if empty
    if ((Test-Path $BinDir) -and ((Get-ChildItem $BinDir | Measure-Object).Count -eq 0)) {
        Remove-Item -Force $BinDir
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
}

if ($Help) {
    Write-Host "Usage: .\install.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Uninstall    Uninstall Commit and remove its isolated environment"
    Write-Host "  -YesPath      Automatically add $BinDir to User PATH without prompting"
    Write-Host "  -NoPath       Do not modify User PATH"
    Write-Host "  -Help         Show this help message"
    Write-Host ""
    Write-Host "Description:"
    Write-Host "  Installs Commit into an isolated virtual environment at:"
    Write-Host "    $VenvDir"
    Write-Host "  and creates a launcher at:"
    Write-Host "    $LauncherPath"
    Write-Host ""
    Write-Host "  Requires Python >= $MinPyMajor.$MinPyMinor. Does NOT require pipx, uv, or admin rights."
    exit 0
}

# ------------------------------------------------------------------------------
# 2. Locate Project Root & Validate pyproject.toml
# ------------------------------------------------------------------------------
$ProjectDir = $PSScriptRoot
if (-not $ProjectDir) {
    $ProjectDir = (Get-Location).Path
}

$PyProjectPath = Join-Path $ProjectDir "pyproject.toml"
if (-not (Test-Path $PyProjectPath)) {
    Write-Error "Error: pyproject.toml not found in: $ProjectDir`nPlease run install.ps1 from the root of the Commit repository or extracted source archive."
    exit 1
}

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host " Commit ($PackageName) Windows Installer" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "Source directory: $ProjectDir"
Write-Host "Target venv:      $VenvDir"
Write-Host "Target launcher:  $LauncherPath"
Write-Host ""

# ------------------------------------------------------------------------------
# 3. Detect Compatible Python Interpreter (>= 3.10)
# ------------------------------------------------------------------------------
$PythonCmd = $null
$PyVersionStr = "not detected"

foreach ($candidate in @("py", "python", "python3")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        try {
            $isCompat = & $candidate -c "import sys; sys.exit(0 if sys.version_info >= ($MinPyMajor, $MinPyMinor) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonCmd = $candidate
                $PyVersionStr = (& $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
                break
            }
        } catch {}
    }
}

if (-not $PythonCmd) {
    Write-Host "Error: Python >= $MinPyMajor.$MinPyMinor was not found on your system." -ForegroundColor Red
    Write-Host ""
    Write-Host "Commit requires Python 3.10 or newer."
    Write-Host "Please install Python from https://www.python.org/downloads/windows/ or the Microsoft Store."
    Write-Host "Make sure to check the option 'Add python.exe to PATH' during installation."
    Write-Host ""
    exit 1
}

Write-Host "Python interpreter: $PythonCmd (version $PyVersionStr)" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 4. Verify Virtual Environment (venv) Support
# ------------------------------------------------------------------------------
try {
    & $PythonCmd -c "import venv" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "venv import failed"
    }
} catch {
    Write-Error "Error: Python 'venv' support is missing from your Python installation.`nPlease reinstall Python with the standard library and virtual environment features enabled."
    exit 1
}

# ------------------------------------------------------------------------------
# 5. Create / Update Isolated Virtual Environment
# ------------------------------------------------------------------------------
if (-not (Test-Path $AppDataDir)) {
    New-Item -ItemType Directory -Path $AppDataDir -Force | Out-Null
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if ((Test-Path $VenvDir) -and (Test-Path $VenvPython)) {
    Write-Host "==> Existing isolated environment detected at $VenvDir" -ForegroundColor Yellow
    Write-Host "==> Updating installation..."
} else {
    Write-Host "==> Creating isolated virtual environment in $VenvDir..." -ForegroundColor Cyan
    if (Test-Path $VenvDir) {
        Remove-Item -Recurse -Force $VenvDir
    }

    & $PythonCmd -m venv "$VenvDir"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "==> Standard venv creation failed; attempting with --without-pip..."
        & $PythonCmd -m venv --without-pip "$VenvDir"
        & $VenvPython -m ensurepip --upgrade --default-pip
    }
}

# Ensure pip is present inside the venv
try {
    & $VenvPython -m pip --version 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "pip missing"
    }
} catch {
    Write-Host "==> Bootstrapping pip inside isolated environment..." -ForegroundColor Cyan
    & $VenvPython -m ensurepip --upgrade --default-pip
}

# ------------------------------------------------------------------------------
# 6. Install Commit into Isolated Environment
# ------------------------------------------------------------------------------
Write-Host "==> Installing Commit dependencies and package..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade --no-warn-script-location "$ProjectDir"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Error: Package installation failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}

# ------------------------------------------------------------------------------
# 7. Create Command Launcher (commit.cmd)
# ------------------------------------------------------------------------------
if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
}

$CommitExeInVenv = Join-Path $VenvDir "Scripts\commit.exe"
$launcherContent = "@echo off`r`n`"$CommitExeInVenv`" %*`r`n"
[System.IO.File]::WriteAllText($LauncherPath, $launcherContent, [System.Text.Encoding]::ASCII)

Write-Host "==> Created launcher: $LauncherPath" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 8. Verify Installation & Version
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "-------------------------------------------------------" -ForegroundColor Cyan
Write-Host " Verification" -ForegroundColor Cyan
Write-Host "-------------------------------------------------------" -ForegroundColor Cyan

if (-not (Test-Path $LauncherPath)) {
    Write-Error "Error: Launcher file was not found: $LauncherPath"
    exit 1
}

try {
    $versionOutput = & $LauncherPath --version 2>&1
    Write-Host "Launcher: $LauncherPath"
    Write-Host "Version:  $versionOutput"
} catch {
    Write-Warning "Could not execute '$LauncherPath --version': $_"
}

# ------------------------------------------------------------------------------
# 9. PATH Verification & Consent-Based Configuration
# ------------------------------------------------------------------------------
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) {
    $userPath = ""
}

$onPath = $false
$currentPathDirs = ($env:PATH -split ";") | ForEach-Object { $_.Trim().TrimEnd("\") }
$binDirNorm = $BinDir.Trim().TrimEnd("\")

if ($currentPathDirs -contains $binDirNorm) {
    $onPath = $true
} else {
    $userPathDirs = ($userPath -split ";") | ForEach-Object { $_.Trim().TrimEnd("\") }
    if ($userPathDirs -contains $binDirNorm) {
        $onPath = $true
    }
}

Write-Host ""
if ($onPath) {
    Write-Host "✓ Commit is installed and immediately available in your PATH!" -ForegroundColor Green
    Write-Host "  Run 'commit' in any Git repository to get started."
} else {
    Write-Host "⚠️  Notice: The directory '$BinDir' is not currently in your User PATH." -ForegroundColor Yellow
    Write-Host ""

    $shouldAddToPath = $false

    if ($YesPath) {
        $shouldAddToPath = $true
    } elseif ($NoPath) {
        $shouldAddToPath = $false
    } else {
        # Check if environment is interactive
        $isInteractive = [Environment]::UserInteractive
        if ($isInteractive) {
            $response = Read-Host "Would you like to add '$BinDir' to your User PATH? [Y/N]"
            if ($response -match "^[yY]([eE][sS])?$") {
                $shouldAddToPath = $true
            }
        }
    }

    if ($shouldAddToPath) {
        try {
            $newPath = if ($userPath) { "$userPath;$BinDir" } else { $BinDir }
            [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
            Write-Host "✓ Added '$BinDir' to your User PATH." -ForegroundColor Green
            Write-Host "  Please open a new Command Prompt or PowerShell window for the change to take effect." -ForegroundColor Yellow
        } catch {
            Write-Warning "Could not update User PATH environment variable: $_"
            Write-Host "To configure manually, add '$BinDir' to your User PATH in Windows Settings."
        }
    } else {
        Write-Host "To run 'commit' from any terminal, add this directory to your User PATH in Windows Settings:"
        Write-Host "  $BinDir" -ForegroundColor Cyan
    }

    Write-Host ""
    Write-Host "To test Commit in your current terminal session immediately without restarting:"
    Write-Host "  `$env:PATH = `"$BinDir;`" + `$env:PATH" -ForegroundColor Cyan
    Write-Host "  commit --version" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Ollama Reminder:" -ForegroundColor Cyan
Write-Host "  Commit requires Ollama to be running locally (or at a configured endpoint)."
Write-Host "  Verify your Ollama service: curl http://localhost:11434/"
Write-Host "  Recommended model:          ollama pull qwen2.5-coder:7b"
Write-Host "=======================================================" -ForegroundColor Cyan
exit 0
