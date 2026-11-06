from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import dotenv
    dotenv.load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass


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
    parser.add_argument(
        "--builder",
        choices=["pyinstaller", "nuitka"],
        default=os.getenv("BUILDER_ENGINE", "pyinstaller").lower(),
        help="Compilation engine: pyinstaller (default) or nuitka (native C++ compilation).",
    )
    parser.add_argument(
        "--arch",
        choices=["both", "x64", "x86"],
        default="both",
        help="Target architecture to compile and package: both (default), x64, or x86.",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Fast development compilation with Nuitka (disables LTO).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean intermediate compiler build cache before compiling.",
    )
    parser.add_argument(
        "--wrapper-version",
        default=os.getenv("APP_WRAPPER_VERSION", os.getenv("WRAPPER_VERSION", "1.0.0")),
        help="Desktop wrapper version sent in the 'X-Wrapper-Version' request header (default: 1.0.0).",
    )
    parser.add_argument(
        "--embed-runtime",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("EMBED_WEBVIEW2_RUNTIME", "true").lower() in ("1", "true", "yes", "on"),
        help="Embed offline WebView2 runtime installers inside setup.exe (default: true).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Keep console window enabled to view stdout/stderr and tracebacks.",
    )
    return parser.parse_args()


def require_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise SystemExit(f"Missing {label}: {resolved}")
    return resolved


def clean_previous_builds(clean_nuitka: bool = False) -> None:
    """Remove generated build products, preserving tools, downloads, and Nuitka cache."""
    generated_directories = [
        PROJECT_ROOT / "dist",
        INSTALLER_ROOT / "builds",
        INSTALLER_ROOT / "staging",
        INSTALLER_ROOT / "output",
    ]
    if clean_nuitka:
        generated_directories.append(PROJECT_ROOT / "build" / "nuitka")

    # Clean PyInstaller intermediate directory if present
    pyi_build = PROJECT_ROOT / "build" / "DIGI Express Admin"
    if pyi_build.is_dir():
        shutil.rmtree(pyi_build, ignore_errors=True)

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


def python_environment(python: Path, architecture: str, builder: str = "pyinstaller") -> dict[str, str]:
    environment = os.environ.copy()
    builder_mod = "nuitka" if builder == "nuitka" else "PyInstaller"
    check = subprocess.run(
        [str(python), "-c", f"import webview, dotenv, {builder_mod}"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        check=False,
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
                [str(python), "-c", f"import webview, dotenv, {builder_mod}"],
                cwd=PROJECT_ROOT,
                env=environment,
                capture_output=True,
                check=False,
            )
            if retry.returncode == 0:
                return environment

    raise SystemExit(
        f"{architecture} Python is missing build dependencies (requires {builder_mod}). "
        f"Install requirements.txt with: {python} -m pip install -r requirements.txt"
    )


def build_app(
    python: Path,
    architecture: str,
    environment: dict[str, str],
    builder: str = "pyinstaller",
    wrapper_version: str = "1.0.0",
    debug: bool = False,
    fast: bool = False,
    clean: bool = False,
) -> Path:
    print(f"\nBuilding {architecture} application with {builder.capitalize()}...")
    command = [
        str(python),
        str(BUILD_SCRIPT),
        "--builder",
        builder,
        "--wrapper-version",
        wrapper_version,
        "--arch",
        architecture,
    ]
    if debug:
        command.append("--debug")
    if fast:
        command.append("--fast")
    if clean:
        command.append("--clean")

    subprocess.run(
        command,
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
    target_arch = args.arch
    build_x64 = target_arch in ("both", "x64")
    build_x86 = target_arch in ("both", "x86")

    x64_python = require_file(args.x64_python, "x64 Python") if build_x64 else None
    x86_python = require_file(args.x86_python, "x86 Python") if build_x86 else None
    iscc = require_file(args.iscc, "Inno Setup compiler")

    x64_environment = python_environment(x64_python, "x64", builder=args.builder) if build_x64 and x64_python else None
    x86_environment = python_environment(x86_python, "x86", builder=args.builder) if build_x86 and x86_python else None

    if build_x64 and x64_python and x64_environment and python_bits(x64_python, x64_environment) != 64:
        raise SystemExit(f"Expected 64-bit Python: {x64_python}")
    if build_x86 and x86_python and x86_environment and python_bits(x86_python, x86_environment) != 32:
        raise SystemExit(f"Expected 32-bit Python: {x86_python}")

    if args.embed_runtime:
        check_arches = []
        if build_x64:
            check_arches.append("X64")
        if build_x86:
            check_arches.append("X86")
        for architecture in check_arches:
            require_file(
                INSTALLER_ROOT
                / "downloads"
                / f"MicrosoftEdgeWebView2RuntimeInstaller{architecture}.exe",
                f"WebView2 {architecture} offline installer",
            )

    clean_previous_builds(clean_nuitka=args.clean)

    x64_app = None
    x86_app = None

    if build_x64 and x64_python and x64_environment:
        x64_app = build_app(
            x64_python,
            "x64",
            x64_environment,
            builder=args.builder,
            wrapper_version=args.wrapper_version,
            debug=args.debug,
            fast=args.fast,
            clean=args.clean,
        )
    if build_x86 and x86_python and x86_environment:
        x86_app = build_app(
            x86_python,
            "x86",
            x86_environment,
            builder=args.builder,
            wrapper_version=args.wrapper_version,
            debug=args.debug,
            fast=args.fast,
            clean=args.clean,
        )

    # For dist output, prefer x64 if built, otherwise x86
    primary_app = x64_app or x86_app
    if primary_app:
        dist_app = PROJECT_ROOT / "dist" / APP_EXE_NAME
        if not dist_app.exists() or dist_app != primary_app:
            shutil.copy2(primary_app, dist_app)
        dist_checksum = sha256_file(dist_app)
        dist_app.with_suffix(dist_app.suffix + ".sha256").write_text(
            f"{dist_checksum}  {dist_app.name}\n",
            encoding="utf-8",
        )

    for architecture, source in (("x86", x86_app), ("x64", x64_app)):
        if source is not None:
            destination = INSTALLER_ROOT / "staging" / architecture / APP_EXE_NAME
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    setup_base_name = "DIGI-Express-Admin-Setup" if target_arch == "both" else f"DIGI-Express-Admin-Setup-{target_arch}"
    embed_runtime_flag = "true" if args.embed_runtime else "false"
    print(f"\nCompiling combined installer (arch: {target_arch}, embed offline runtime: {embed_runtime_flag})...")
    iscc_command = [
        str(iscc),
        f"/DAppVersion={args.wrapper_version}",
        f"/DEmbedWebView2Runtime={embed_runtime_flag}",
        f"/DSingleArch={target_arch}",
        f"/DOutputBaseFilename={setup_base_name}",
        str(INSTALLER_ROOT / "DIGI Express Admin.iss"),
    ]
    subprocess.run(
        iscc_command,
        cwd=INSTALLER_ROOT,
        check=True,
    )

    installer = require_file(
        INSTALLER_ROOT / "output" / f"{setup_base_name}.exe",
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
