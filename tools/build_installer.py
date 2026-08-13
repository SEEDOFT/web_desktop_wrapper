from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = PROJECT_ROOT / "installer"
APP_EXE_NAME = "DIGI Express Admin.exe"
BUILD_SCRIPT = PROJECT_ROOT / "tools" / "build.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build x64 and x86 application executables, then package one "
            "offline Windows installer containing both WebView2 runtimes."
        )
    )
    parser.add_argument(
        "--x64-python",
        type=Path,
        default=Path(sys.executable),
        help="64-bit Python executable. Defaults to the Python running this script.",
    )
    parser.add_argument(
        "--x86-python",
        type=Path,
        default=PROJECT_ROOT / ".build-tools" / "python-x86" / "python.exe",
        help="Workspace-local 32-bit Python executable.",
    )
    parser.add_argument(
        "--iscc",
        type=Path,
        default=Path(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        )
        / "Inno Setup 6"
        / "ISCC.exe",
        help="Inno Setup command-line compiler.",
    )
    return parser.parse_args()


def require_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise SystemExit(f"Missing {label}: {resolved}")
    return resolved


def clean_previous_builds() -> None:
    """Remove only generated build products, preserving tools and downloads."""
    generated_directories = (
        PROJECT_ROOT / "build",
        PROJECT_ROOT / "dist",
        INSTALLER_ROOT / "builds",
        INSTALLER_ROOT / "staging",
        INSTALLER_ROOT / "output",
    )
    generated_files = (
        PROJECT_ROOT / "DIGI Express Admin.spec",
    )

    print("Cleaning previous build artifacts...")
    for directory in generated_directories:
        resolved = directory.resolve()
        if PROJECT_ROOT not in resolved.parents:
            raise SystemExit(f"Refusing to clean path outside project: {resolved}")
        if resolved.is_dir():
            shutil.rmtree(resolved)
            print(f"  Removed directory: {resolved}")

    for file in generated_files:
        resolved = file.resolve()
        if PROJECT_ROOT not in resolved.parents:
            raise SystemExit(f"Refusing to clean path outside project: {resolved}")
        if resolved.is_file():
            resolved.unlink()
            print(f"  Removed file: {resolved}")


def python_bits(python: Path, environment: dict[str, str]) -> int:
    result = subprocess.run(
        [str(python), "-c", "import struct; print(struct.calcsize('P') * 8)"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def python_environment(python: Path, architecture: str) -> dict[str, str]:
    environment = os.environ.copy()
    check = subprocess.run(
        [str(python), "-c", "import webview, dotenv, PyInstaller"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
    )
    if check.returncode == 0:
        return environment

    if architecture == "x64":
        fallback_packages = PROJECT_ROOT / ".venv" / "Lib" / "site-packages"
        if fallback_packages.is_dir():
            current = environment.get("PYTHONPATH", "")
            environment["PYTHONPATH"] = str(fallback_packages) + (
                os.pathsep + current if current else ""
            )
            retry = subprocess.run(
                [str(python), "-c", "import webview, dotenv, PyInstaller"],
                cwd=PROJECT_ROOT,
                env=environment,
                capture_output=True,
            )
            if retry.returncode == 0:
                return environment

    raise SystemExit(
        f"{architecture} Python is missing build dependencies. "
        f"Install requirements.txt with: {python} -m pip install -r requirements.txt"
    )


def build_app(
    python: Path,
    architecture: str,
    environment: dict[str, str],
) -> Path:
    print(f"\nBuilding {architecture} application...")
    subprocess.run(
        [str(python), str(BUILD_SCRIPT)],
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
    )
    output = require_file(PROJECT_ROOT / "dist" / APP_EXE_NAME, architecture)
    destination = INSTALLER_ROOT / "builds" / architecture / APP_EXE_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, destination)
    return destination


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    x64_python = require_file(args.x64_python, "x64 Python")
    x86_python = require_file(args.x86_python, "x86 Python")
    iscc = require_file(args.iscc, "Inno Setup compiler")

    x64_environment = python_environment(x64_python, "x64")
    x86_environment = python_environment(x86_python, "x86")
    if python_bits(x64_python, x64_environment) != 64:
        raise SystemExit(f"Expected 64-bit Python: {x64_python}")
    if python_bits(x86_python, x86_environment) != 32:
        raise SystemExit(f"Expected 32-bit Python: {x86_python}")

    for architecture in ("X86", "X64"):
        require_file(
            INSTALLER_ROOT
            / "downloads"
            / f"MicrosoftEdgeWebView2RuntimeInstaller{architecture}.exe",
            f"WebView2 {architecture} offline installer",
        )

    clean_previous_builds()

    x64_app = build_app(x64_python, "x64", x64_environment)
    x86_app = build_app(x86_python, "x86", x86_environment)

    # Keep the conventional standalone dist output as x64 after both builds.
    dist_app = PROJECT_ROOT / "dist" / APP_EXE_NAME
    shutil.copy2(x64_app, dist_app)
    dist_checksum = sha256_file(dist_app)
    dist_app.with_suffix(dist_app.suffix + ".sha256").write_text(
        f"{dist_checksum}  {dist_app.name}\n",
        encoding="utf-8",
    )

    for architecture, source in (("x86", x86_app), ("x64", x64_app)):
        destination = INSTALLER_ROOT / "staging" / architecture / APP_EXE_NAME
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    print("\nCompiling combined offline installer...")
    subprocess.run(
        [str(iscc), str(INSTALLER_ROOT / "DIGI Express Admin.iss")],
        cwd=INSTALLER_ROOT,
        check=True,
    )

    installer = require_file(
        INSTALLER_ROOT / "output" / "DIGI-Express-Admin-Setup.exe",
        "compiled installer",
    )
    checksum = sha256_file(installer)
    installer.with_suffix(installer.suffix + ".sha256").write_text(
        f"{checksum}  {installer.name}\n",
        encoding="utf-8",
    )
    print(f"\nBuild complete: {installer}")
    print(f"SHA-256: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
