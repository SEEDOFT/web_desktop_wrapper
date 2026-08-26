#!/usr/bin/env bash
# Cleans all generated dependencies, caches, and build artifacts.
#
# Usage:
#   bash tools/cleanup.sh
#   ./tools/cleanup.sh --skip-zip
#   ./tools/cleanup.sh --output-dir ~/Desktop

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

SKIP_ZIP=false
OUTPUT_DIR=".."

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-zip)
            SKIP_ZIP=true
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: $0 [--skip-zip] [--output-dir <path>]"
            exit 1
            ;;
    esac
done

echo "Removing generated build artifacts and caches from ${ROOT_DIR} ..."

GENERATED_PATHS=(
    "build"
    "dist"
    "installer/builds"
    "installer/downloads"
    "installer/output"
    "installer/staging"
    "macos/output"
    "macos/staging"
    "nuitka-crash-report.xml"
)

for path in "${GENERATED_PATHS[@]}"; do
    if [[ -e "${path}" ]]; then
        rm -rf "${path}"
        echo "  Removed: ${path}"
    fi
done

# Remove __pycache__, spec files, DS_Store, and macOS resource forks
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.spec" -delete 2>/dev/null || true
find . -type f -name ".DS_Store" -delete 2>/dev/null || true
find . -type f -name "._*" -delete 2>/dev/null || true

echo "Removed leftover __pycache__/, *.spec, and macOS metadata."

if [[ "${SKIP_ZIP}" == "true" ]]; then
    echo "Cleanup complete."
    exit 0
fi

if ! command -v tar &>/dev/null; then
    echo "tar not found; skipping ZIP creation."
    exit 0
fi

BASE_NAME="$(basename "${ROOT_DIR}")_source"
ZIP_PATH="${OUTPUT_DIR}/${BASE_NAME}.zip"

if [[ -f "${ZIP_PATH}" ]]; then
    rm -f "${ZIP_PATH}"
fi

echo "Creating source ZIP: ${ZIP_PATH}"
tar -a -c -f "${ZIP_PATH}" --exclude=".git" --exclude="*.zip" --exclude=".venv" .

if [[ -f "${ZIP_PATH}" ]]; then
    SIZE_BYTES=$(stat -f%z "${ZIP_PATH}" 2>/dev/null || stat -c%s "${ZIP_PATH}" 2>/dev/null || echo 0)
    SIZE_MB=$(awk "BEGIN {printf \"%.2f\", ${SIZE_BYTES}/1048576}")
    echo "Done. Clean source ZIP: ${ZIP_PATH} (${SIZE_MB} MB)"
fi
