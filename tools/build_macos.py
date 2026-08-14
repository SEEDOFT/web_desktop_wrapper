from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import AppConfig  # noqa: E402


EMBEDDED_CONFIG_PATH = PROJECT_ROOT / "app" / "embedded_config.py"
APP_NAME = "DIGI Express Admin"
BUNDLE_ID = "com.digiexpress.admin"
MACOS_ROOT = PROJECT_ROOT / "macos"
OUTPUT_ROOT = MACOS_ROOT / "output"
APP_PATH = PROJECT_ROOT / "dist" / f"{APP_NAME}.app"
DMG_PATH = OUTPUT_ROOT / "DIGI-Express-Admin-macOS-universal.dmg"
ZIP_PATH = OUTPUT_ROOT / "DIGI-Express-Admin-macOS-universal.app.zip"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the universal macOS app and unsigned DMG."
    )
    parser.add_argument("--skip-dmg", action="store_true")
    return parser.parse_args()


def run(
    command: list[str],
    *,
    environment: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=check, text=True, capture_output=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksum(path: Path) -> None:
    checksum = sha256_file(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{checksum}  {path.name}\n",
        encoding="utf-8",
    )
    print(f"SHA-256 ({path.name}): {checksum}")


def clean_previous_builds() -> None:
    for directory in (
        PROJECT_ROOT / "build",
        PROJECT_ROOT / "dist",
        MACOS_ROOT / "staging",
        OUTPUT_ROOT,
    ):
        if directory.is_dir():
            shutil.rmtree(directory)
    spec = PROJECT_ROOT / f"{APP_NAME}.spec"
    if spec.is_file():
        spec.unlink()


def validate_environment() -> None:
    if sys.platform != "darwin":
        raise SystemExit("The macOS application must be built on macOS.")

    for command in ("lipo", "iconutil", "hdiutil", "ditto", "codesign", "xattr"):
        if shutil.which(command) is None:
            raise SystemExit(f"Missing required macOS build tool: {command}")

    try:
        import Cocoa  # noqa: F401
        import PyInstaller  # noqa: F401
        import Quartz  # noqa: F401
        import Security  # noqa: F401
        import WebKit  # noqa: F401
        import webview  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Missing macOS dependencies. Run: "
            "python3 -m pip install -r requirements-macos.txt"
        ) from exc

    result = subprocess.run(
        ["lipo", "-archs", sys.executable],
        check=True,
        capture_output=True,
        text=True,
    )
    architectures = set(result.stdout.split())
    if not {"arm64", "x86_64"}.issubset(architectures):
        raise SystemExit(
            "Universal2 Python is required; current Python architectures: "
            + ", ".join(sorted(architectures))
        )


def embedded_payload() -> dict[str, object]:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    config = AppConfig.load()
    parsed = urlparse(config.web_app_url)
    if parsed.query or parsed.fragment:
        raise SystemExit("WEB_APP_URL must not contain a query string or fragment.")
    return {
        "app_name": config.app_name,
        "organization_name": config.organization_name,
        "web_app_url": config.web_app_url,
        "allowed_hosts": list(config.allowed_hosts),
        "allow_subdomains": config.allow_subdomains,
        "open_external_links": config.open_external_links,
        "allow_insecure_http": config.allow_insecure_http,
        "start_maximized": config.start_maximized,
        "window_width": config.window_width,
        "window_height": config.window_height,
        "persist_session": config.persist_session,
        "allow_downloads": config.allow_downloads,
        "page_background_color": config.page_background_color,
        "app_icon": "assets/digi_express.icns",
    }


def write_embedded_config(payload: dict[str, object]) -> None:
    EMBEDDED_CONFIG_PATH.write_text(
        '"""Generated temporarily by tools/build_macos.py."""\n\n'
        f"CONFIG = {payload!r}\n",
        encoding="utf-8",
    )


def generate_icon() -> Path:
    source = PROJECT_ROOT / "assets" / "digi_portrait.jpg"
    if not source.is_file():
        source = PROJECT_ROOT / "assets" / "digi_landscape.jpg"
    if not source.is_file():
        raise SystemExit("Missing source artwork for the macOS application icon.")

    iconset = MACOS_ROOT / "staging" / "digi_express.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    sizes = ((16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2))
    for size, scale in sizes:
        pixels = size * scale
        suffix = "@2x" if scale == 2 else ""
        destination = iconset / f"icon_{size}x{size}{suffix}.png"
        run(["sips", "-s", "format", "png", "-z", str(pixels), str(pixels), str(source), "--out", str(destination)])

    icon = PROJECT_ROOT / "assets" / "digi_express.icns"
    run(["iconutil", "-c", "icns", str(iconset), "-o", str(icon)])
    return icon


def configure_bundle() -> None:
    plist_path = APP_PATH / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        plist = plistlib.load(handle)
    plist["LSMinimumSystemVersion"] = "12.0"
    plist["CFBundleIdentifier"] = BUNDLE_ID
    plist["NSHighResolutionCapable"] = True
    with plist_path.open("wb") as handle:
        plistlib.dump(plist, handle)


def sign_bundle(path: Path) -> None:
    run(["codesign", "--force", "--deep", "--sign", "-", "--options", "runtime", str(path)])
    result = run(["xattr", "-d", "com.apple.quarantine", str(path)], check=False)
    if result.returncode not in (0, 1):
        raise SystemExit(
            f"Failed to clear quarantine flag for {path}: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )


def create_distribution(skip_dmg: bool) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(APP_PATH), str(ZIP_PATH)])
    write_checksum(ZIP_PATH)
    if skip_dmg:
        return

    staging = MACOS_ROOT / "staging" / "dmg"
    staging.mkdir(parents=True, exist_ok=True)
    shutil.copytree(APP_PATH, staging / APP_PATH.name)
    (staging / "Applications").symlink_to("/Applications")
    run(["hdiutil", "create", "-volname", APP_NAME, "-srcfolder", str(staging), "-ov", "-format", "UDZO", str(DMG_PATH)])
    sign_bundle(DMG_PATH)
    write_checksum(DMG_PATH)


def main() -> int:
    args = parse_args()
    validate_environment()
    clean_previous_builds()
    icon = generate_icon()
    payload = embedded_payload()
    original_content = EMBEDDED_CONFIG_PATH.read_text(encoding="utf-8")
    environment = os.environ.copy()
    environment["MACOSX_DEPLOYMENT_TARGET"] = "12.0"
    try:
        write_embedded_config(payload)
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--windowed",
                "--noupx",
                "--name",
                APP_NAME,
                "--osx-bundle-identifier",
                BUNDLE_ID,
                "--target-architecture",
                "universal2",
                "--icon",
                str(icon),
                "--paths",
                str(PROJECT_ROOT),
                "--hidden-import",
                "webview.platforms.cocoa",
                "--collect-all",
                "webview",
                "--add-data",
                f"{PROJECT_ROOT / 'assets'}:assets",
                str(PROJECT_ROOT / "app" / "__main__.py"),
            ],
            environment=environment,
        )
    finally:
        EMBEDDED_CONFIG_PATH.write_text(original_content, encoding="utf-8")

    configure_bundle()
    sign_bundle(APP_PATH)
    run(["lipo", "-info", str(APP_PATH / "Contents" / "MacOS" / APP_NAME)])
    create_distribution(args.skip_dmg)
    print(f"Build complete: {DMG_PATH if not args.skip_dmg else ZIP_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
