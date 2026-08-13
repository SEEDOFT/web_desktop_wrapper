from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = PROJECT_ROOT / "installer"
APP_EXE = "DIGI Express Admin.exe"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package x86/x64 app builds and offline WebView2 runtimes."
    )
    parser.add_argument("--x86-exe", type=Path, required=True)
    parser.add_argument("--x64-exe", type=Path, required=True)
    parser.add_argument(
        "--iscc",
        type=Path,
        default=Path(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        )
        / "Inno Setup 6"
        / "ISCC.exe",
        help="Path to the Inno Setup command-line compiler.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise SystemExit(f"Missing {label}: {resolved}")
    return resolved


def main() -> int:
    args = parse_args()
    x86_exe = require_file(args.x86_exe, "x86 application executable")
    x64_exe = require_file(args.x64_exe, "x64 application executable")
    iscc = require_file(args.iscc, "Inno Setup compiler")

    for architecture, source in (("x86", x86_exe), ("x64", x64_exe)):
        destination = INSTALLER_ROOT / "staging" / architecture / APP_EXE
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    for architecture in ("X86", "X64"):
        require_file(
            INSTALLER_ROOT
            / "downloads"
            / f"MicrosoftEdgeWebView2RuntimeInstaller{architecture}.exe",
            f"WebView2 {architecture} offline installer",
        )

    subprocess.run(
        [str(iscc), str(INSTALLER_ROOT / "DIGI Express Admin.iss")],
        cwd=INSTALLER_ROOT,
        check=True,
    )

    output = INSTALLER_ROOT / "output" / "DIGI-Express-Admin-Setup.exe"
    checksum = sha256_file(output)
    checksum_file = output.with_suffix(output.suffix + ".sha256")
    checksum_file.write_text(f"{checksum}  {output.name}\n", encoding="utf-8")
    print(f"Installer: {output}")
    print(f"SHA-256: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
