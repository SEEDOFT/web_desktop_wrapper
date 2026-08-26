<#
.SYNOPSIS
    Complete end-to-end setup and build pipeline for Windows (PowerShell).

.DESCRIPTION
    Automates environment configuration (.env), virtual environment creation (.venv),
    dependency installation (requirements.txt), and application compilation using
    either Nuitka (C++ machine code) or PyInstaller.

.PARAMETER Builder
    Compilation engine to use: 'nuitka' (default) or 'pyinstaller'.

.PARAMETER Installer
    Build the full dual-architecture (x64 + x86) offline Windows Setup installer
    via Inno Setup instead of just the standalone executable.

.PARAMETER Debug
    Keep console window attached to view stdout/stderr and tracebacks.

.EXAMPLE
    .\build.ps1
    .\build.ps1 -Builder nuitka
    .\build.ps1 -Installer
    .\build.ps1 -Builder nuitka -Installer
#>

[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("nuitka", "pyinstaller")]
    [string]$Builder,

    [switch]$Installer,

    [switch]$Debug,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $RootDir

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "       DIGI Web Desktop Wrapper - Windows Build Pipeline         " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# ── Step 1: Environment Configuration ──────────────────────────────────────────
$envPath = Join-Path $RootDir ".env"
$envExamplePath = Join-Path $RootDir ".env.example"

if (-not (Test-Path -LiteralPath $envPath)) {
    if (Test-Path -LiteralPath $envExamplePath) {
        Write-Host "[1/4] Copying .env.example -> .env ..." -ForegroundColor Yellow
        Copy-Item -LiteralPath $envExamplePath -Destination $envPath
    } else {
        Write-Error "[ERROR] Neither .env nor .env.example found in $RootDir!"
        exit 1
    }
} else {
    Write-Host "[1/4] Using existing .env configuration." -ForegroundColor Green
}

# Determine default builder from .env if not explicitly specified via param
if (-not $PSBoundParameters.ContainsKey("Builder")) {
    $envContent = Get-Content -LiteralPath $envPath -ErrorAction SilentlyContinue
    $builderLine = $envContent | Where-Object { $_ -match "^\s*BUILDER_ENGINE\s*=\s*(.+)$" } | Select-Object -Last 1
    if ($builderLine -and ($builderLine -match "^\s*BUILDER_ENGINE\s*=\s*(.+)$")) {
        $Builder = $Matches[1].Trim().ToLower()
    } else {
        $Builder = "nuitka"
    }
}

# ── Step 2: Python Virtual Environment Setup ──────────────────────────────────
$venvDir = Join-Path $RootDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[2/4] Creating virtual environment (.venv) ..." -ForegroundColor Yellow
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        Write-Error "[ERROR] Failed to create virtual environment. Ensure Python 3.10+ is installed and on PATH."
        exit 1
    }
} else {
    Write-Host "[2/4] Using existing virtual environment (.venv)." -ForegroundColor Green
}

# ── Step 3: Install Windows Requirements ──────────────────────────────────────
Write-Host "[3/4] Installing / updating dependencies from requirements.txt ..." -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r (Join-Path $RootDir "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "[ERROR] Failed to install requirements."
    exit 1
}

# ── Step 4: Run Windows Build ──────────────────────────────────────────────────
$buildScriptArgs = @()

if ($Installer) {
    Write-Host "[4/4] Building Windows Setup installer via Inno Setup (Builder: $Builder) ..." -ForegroundColor Cyan
    $targetScript = Join-Path $RootDir "tools\build_installer.py"
    $buildScriptArgs += "--builder", $Builder
    if ($Debug) {
        $buildScriptArgs += "--debug"
    }
} else {
    Write-Host "[4/4] Building standalone Windows executable (Builder: $Builder) ..." -ForegroundColor Cyan
    $targetScript = Join-Path $RootDir "tools\build.py"
    $buildScriptArgs += "--builder", $Builder
    if ($Debug) {
        $buildScriptArgs += "--debug"
    }
}

if ($ExtraArgs) {
    $buildScriptArgs += $ExtraArgs
}

& $venvPython $targetScript @buildScriptArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "[ERROR] Build failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}

Write-Host "=================================================================" -ForegroundColor Green
Write-Host " [SUCCESS] Build completed successfully!" -ForegroundColor Green
if ($Installer) {
    Write-Host " Output installer located in: $(Join-Path $RootDir 'installer\output')" -ForegroundColor Green
} else {
    Write-Host " Output executable located in: $(Join-Path $RootDir 'dist')" -ForegroundColor Green
}
Write-Host "=================================================================" -ForegroundColor Green
