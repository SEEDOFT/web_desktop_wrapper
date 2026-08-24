# Cleans all generated dependencies and build artifacts so the project folder
# can be zipped and shared as a clean source snapshot. Works on Windows
# (PowerShell) and macOS (pwsh / PowerShell 7+).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools/cleanup.ps1
#   pwsh -File tools/cleanup.ps1 -SkipZip
#   pwsh -File tools/cleanup.ps1 -OutputDir ~/shares

[CmdletBinding()]
param(
    [switch]$SkipZip,
    [string]$OutputDir = ".."
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$onWindows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [System.Runtime.InteropServices.OSPlatform]::Windows
)

# Everything listed here is regenerated from source (see .gitignore and the
# build scripts) and is safe to delete before sharing.
$generated = @(
    ".venv",
    ".build-tools",
    "build",
    "dist",
    "installer/builds",
    "installer/downloads",
    "installer/output",
    "installer/staging",
    "macos/output",
    "macos/staging",
    ".env",
    "nuitka-crash-report.xml"
)

Write-Host "Removing generated dependencies and build artifacts from $root ..."
foreach ($path in $generated) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
        Write-Host "  Removed: $path"
    }
}

Get-ChildItem -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath "assets" -Filter "*.icns" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath "." -Filter "*.spec" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

if (-not $onWindows) {
    # macOS-only leftovers: Finder metadata and macOS-specific caches.
    Get-ChildItem -Recurse -Force -Filter ".DS_Store" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Force -Filter "._*" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

Write-Host "Removed leftover __pycache__/, *.icns, *.spec, and platform metadata."

if ($SkipZip) {
    Write-Host "Cleanup complete. Project size: $([math]::Round((Get-ChildItem -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 2)) MB"
    exit 0
}

if (-not (Get-Command tar -ErrorAction SilentlyContinue)) {
    Write-Host "tar not found; skipping ZIP creation." -ForegroundColor Yellow
    exit 0
}

$baseName = (Split-Path -Leaf $root) + "_source"
$zipPath = Join-Path $OutputDir ($baseName + ".zip")
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Write-Host "Creating source ZIP: $zipPath"
tar -a -c -f $zipPath --exclude=".git" --exclude="*.zip" .

$sizeMB = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 2)
Write-Host "Done. ZIP: $zipPath ($sizeMB MB)"
