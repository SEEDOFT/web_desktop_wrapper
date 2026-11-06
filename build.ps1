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
    Build offline Windows Setup installer via Inno Setup instead of just the standalone executable.

.PARAMETER Fast
    Fast development build with Nuitka (disables LTO, builds standalone directory for quick iteration).

.PARAMETER Clean
    Clean cached compiler intermediate build artifacts before compiling.

.PARAMETER Arch
    Target architecture to compile: 'both' (default for installer), 'x64', or 'x86'.

.PARAMETER Reinstall
    Force reinstallation of dependencies from requirements.txt even if unchanged.

.PARAMETER Debug
    Keep console window attached to view stdout/stderr and tracebacks.

.EXAMPLE
    .\build.ps1
    .\build.ps1 -Builder nuitka -Fast
    .\build.ps1 -Builder nuitka -Clean
    .\build.ps1 -Installer -Arch x64
    .\build.ps1 -Builder nuitka -Installer
#>

[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("nuitka", "pyinstaller")]
    [string]$Builder,

    [switch]$Installer,

    [switch]$Fast,

    [switch]$Clean,

    [ValidateSet("both", "x64", "x86")]
    [string]$Arch = "both",

    [switch]$Reinstall,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

# CmdletBinding supplies -Debug as a common parameter; do not redeclare it.
$debugBuild = $PSBoundParameters.ContainsKey("Debug") -and [bool]$PSBoundParameters["Debug"]

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
$reqFile = Join-Path $RootDir "requirements.txt"
$reqStampFile = Join-Path $venvDir ".requirements.sha256"
$currentReqHash = (Get-FileHash -LiteralPath $reqFile -Algorithm SHA256).Hash
$cachedReqHash = if (Test-Path -LiteralPath $reqStampFile) { (Get-Content -LiteralPath $reqStampFile -ErrorAction SilentlyContinue).Trim() } else { "" }

if ($Reinstall -or ($currentReqHash -ne $cachedReqHash)) {
    Write-Host "[3/4] Installing / updating dependencies from requirements.txt ..." -ForegroundColor Yellow
    & $venvPython -m pip install -r $reqFile --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "[ERROR] Failed to install requirements."
        exit 1
    }
    Set-Content -LiteralPath $reqStampFile -Value $currentReqHash -Encoding utf8
} else {
    Write-Host "[3/4] Dependencies up-to-date (skipping pip install). Use -Reinstall to force." -ForegroundColor Green
}

# ── Step 4: Run Windows Build ──────────────────────────────────────────────────
$buildScriptArgs = @()

if ($Installer) {
    Write-Host "[4/4] Building Windows Setup installer via Inno Setup (Builder: $Builder, Arch: $Arch) ..." -ForegroundColor Cyan
    $targetScript = Join-Path $RootDir "tools\build_installer.py"
    $buildScriptArgs += "--builder", $Builder
    $buildScriptArgs += "--arch", $Arch
    if ($Fast) {
        $buildScriptArgs += "--fast"
    }
    if ($Clean) {
        $buildScriptArgs += "--clean"
    }
    if ($debugBuild) {
        $buildScriptArgs += "--debug"
    }
} else {
    $modeTag = if ($Fast) { " [Fast mode]" } else { "" }
    Write-Host "[4/4] Building standalone Windows executable (Builder: $Builder$modeTag) ..." -ForegroundColor Cyan
    $targetScript = Join-Path $RootDir "tools\build.py"
    $buildScriptArgs += "--builder", $Builder
    if ($Arch -and $Arch -ne "both") {
        $buildScriptArgs += "--arch", $Arch
    }
    if ($Fast) {
        $buildScriptArgs += "--fast"
    }
    if ($Clean) {
        $buildScriptArgs += "--clean"
    }
    if ($debugBuild) {
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
