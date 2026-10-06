#!/usr/bin/env bash
# Complete end-to-end setup and build script for macOS with Nuitka compilation.
#
# Usage:
#   bash tools/build_nuitka_all.sh
#   ./tools/build_nuitka_all.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

echo "================================================================="
echo "       DIGI Web Desktop Wrapper - macOS Nuitka Build Pipeline    "
echo "================================================================="

# Step 1: Environment configuration
if [[ ! -f ".env" ]]; then
    if [[ -f ".env.example" ]]; then
        echo "[1/4] Copying .env.example -> .env ..."
        cp .env.example .env
    else
        echo "[ERROR] Neither .env nor .env.example found!"
        exit 1
    fi
else
    echo "[1/4] Using existing .env configuration."
fi

# Step 2: Python Virtual Environment Setup
VENV_DIR="${ROOT_DIR}/.venv"
if [[ ! -d "${VENV_DIR}" ]]; then
    echo "[2/4] Creating virtual environment (.venv) ..."
    python3 -m venv "${VENV_DIR}"
else
    echo "[2/4] Using existing virtual environment (.venv)."
fi

# Activate virtual environment
source "${VENV_DIR}/bin/activate"

# Step 3: Install macOS and project dependencies
echo "[3/4] Installing pinned dependencies from requirements-macos.lock.txt ..."
python3 -m pip install -r requirements-macos.lock.txt --quiet

# Step 4: Run macOS Nuitka Build
echo "[4/4] Building standalone macOS application with Nuitka C++ compiler ..."
python3 tools/build_macos.py --builder nuitka "$@"

echo "================================================================="
echo " [SUCCESS] Build completed successfully!"
echo " Output artifacts located in: ${ROOT_DIR}/macos/output/"
echo "================================================================="
