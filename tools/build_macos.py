from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import AppConfig  # noqa: E402
from tools.build import (  # noqa: E402
    normalize_local_url,
    safe_executable_name,
    validate_url,
)


EMBEDDED_CONFIG_PATH = PROJECT_ROOT / "app" / "embedded_config.py"
DEFAULT_APP_NAME = "DIGI Express Admin"
DEFAULT_BUNDLE_ID = "com.digiexpress.admin"
MACOS_ROOT = PROJECT_ROOT / "macos"
OUTPUT_ROOT = MACOS_ROOT / "output"
ENV_PATH = PROJECT_ROOT / ".env"


def load_build_environment() -> None:
    """Load build-time defaults before argparse reads environment variables."""
    if ENV_PATH.is_file():
        load_dotenv(ENV_PATH, override=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the universal macOS app, unsigned DMG, and ZIP archive."
    )
    parser.add_argument(
        "--url",
        help="HTTPS web application URL. Defaults to WEB_APP_URL from .env.",
    )
    parser.add_argument(
        "--name",
        help="Desktop application name. Defaults to APP_NAME from .env.",
    )
    parser.add_argument(
        "--organization",
        help="Organization name. Defaults to APP_ORGANIZATION from .env.",
    )
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        help="Additional exact navigation host. Repeat as needed.",
    )
    parser.add_argument(
        "--allow-subdomains",
        action="store_true",
        help="Allow subdomains of approved hosts.",
    )
    parser.add_argument(
        "--open-external-links",
        action="store_true",
        help="Open non-approved links in the system browser.",
    )
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Permit remote HTTP. This weakens transport security.",
    )
    parser.add_argument(
        "--persist-session",
        action="store_true",
        help="Persist cookies and disk cache between launches.",
    )
    parser.add_argument(
        "--allow-downloads",
        action="store_true",
        help="Allow the web application to save files to disk.",
    )
    parser.add_argument(
        "--windowed-size",
        nargs=2,
        type=int,
        metavar=("WIDTH", "HEIGHT"),
        default=None,
        help="Initial window size when START_MAXIMIZED=false.",
    )
    parser.add_argument(
        "--not-maximized",
        action="store_true",
        help="Start as a normal window instead of maximized.",
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Build a directory bundle instead of the default single-file app bundle.",
    )
    parser.add_argument(
        "--icon",
        type=Path,
        help="Path to a .icns application icon. Defaults to assets/digi_express.icns.",
    )
    parser.add_argument(
        "--builder",
        choices=["pyinstaller", "nuitka"],
        default=os.getenv("BUILDER_ENGINE", "pyinstaller").lower(),
        help=(
            "Compilation engine: pyinstaller (default, universal2) or "
            "nuitka (native C++ compilation; native host architecture only)."
        ),
    )
    parser.add_argument(
        "--wrapper-version",
        default=os.getenv("APP_WRAPPER_VERSION", os.getenv("WRAPPER_VERSION", "1.0.0")),
        help="Desktop wrapper version sent in the 'X-Wrapper-Version' request header (default: 1.0.0).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Keep the console visible to view stdout/stderr and tracebacks.",
    )
    parser.add_argument("--skip-dmg", action="store_true", help="Build the .app and ZIP only.")
    parser.add_argument(
        "--skip-quarantine-strip",
        action="store_true",
        help="Skip stripping com.apple.quarantine from the project and toolchain before building.",
    )
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


def strip_source_quarantine() -> None:
    """Recursively strip com.apple.quarantine and extended attributes from the
    project tree and the local build toolchain.

    Files downloaded from the internet (e.g. a cloned repository or pip wheels)
    carry the com.apple.quarantine attribute. Gatekeeper can then block tools
    and the interpreter mid-build on later runs, causing intermittent failures
    that look unrelated to the code. Stripping the attribute up front keeps the
    build working reliably over long periods of time.

    If permission is denied (e.g. a read-only system path), the error is
    reported as a warning instead of aborting the build.
    """
    print("Stripping quarantine and extended attributes from the project and toolchain...")

    targets: list[Path] = [PROJECT_ROOT, Path(sys.executable).resolve()]
    if sys.base_prefix:
        targets.append(Path(sys.base_prefix).resolve())
    for tool in ("lipo", "iconutil", "hdiutil", "ditto", "codesign", "xattr", "sips", "nuitka"):
        tool_path = shutil.which(tool)
        if tool_path:
            targets.append(Path(tool_path).resolve())

    seen: set[Path] = set()
    for target in targets:
        if target in seen or not target.exists():
            continue
        seen.add(target)
        try:
            remove_quarantine(target)
        except Exception as exc:  # pragma: no cover - depends on host FS
            print(f"[WARN] Could not strip quarantine from {target}: {exc}", file=sys.stderr)


def clean_previous_builds() -> None:
    for directory in (
        PROJECT_ROOT / "build",
        PROJECT_ROOT / "dist",
        MACOS_ROOT / "staging",
        OUTPUT_ROOT,
    ):
        if directory.is_dir():
            shutil.rmtree(directory)
    for spec in PROJECT_ROOT.glob("*.spec"):
        spec.unlink()


def validate_environment(builder: str) -> None:
    # Use the runtime platform API so Windows-based type checkers do not mark
    # the remainder of this macOS-only validation function as unreachable.
    if platform.system() != "Darwin":
        raise SystemExit("The macOS application must be built on macOS.")

    for command in ("lipo", "iconutil", "hdiutil", "ditto", "codesign", "xattr"):
        if shutil.which(command) is None:
            raise SystemExit(f"Missing required macOS build tool: {command}")

    try:
        import Cocoa  # noqa: F401
        import Quartz  # noqa: F401
        import Security  # noqa: F401
        import WebKit  # noqa: F401
        import webview  # noqa: F401
        if builder == "pyinstaller":
            import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Missing macOS dependencies. Run: "
            "python3 -m pip install -r requirements-macos.txt"
        ) from exc

    if builder == "pyinstaller":
        result = subprocess.run(
            ["lipo", "-archs", sys.executable],
            check=True,
            capture_output=True,
            text=True,
        )
        architectures = set(result.stdout.split())
        if not {"arm64", "x86_64"}.issubset(architectures):
            raise SystemExit(
                "Universal2 Python is required for the PyInstaller build; "
                "current Python architectures: "
                + ", ".join(sorted(architectures))
            )


def embedded_payload(args: argparse.Namespace) -> dict[str, object]:
    load_build_environment()
    config = AppConfig.load()

    allow_insecure_http = args.allow_insecure_http or config.allow_insecure_http
    web_app_url = normalize_local_url(args.url or config.web_app_url)
    try:
        primary_host = validate_url(web_app_url, allow_insecure_http)
    except ValueError as exc:
        raise SystemExit(f"Configuration error: {exc}")

    app_name = (args.name or config.app_name).strip() or DEFAULT_APP_NAME
    organization_name = (args.organization or config.organization_name).strip()
    safe_executable_name(app_name)

    allowed_hosts = set(config.allowed_hosts)
    allowed_hosts.add(primary_host)
    allowed_hosts.update(
        host.strip().lower().rstrip(".")
        for host in args.allowed_host
        if host.strip()
    )

    if args.windowed_size is not None:
        width, height = args.windowed_size
        if not (800 <= width <= 7680 and 600 <= height <= 4320):
            raise SystemExit(
                "Configuration error: width must be 800-7680 and height 600-4320."
            )
    else:
        width, height = config.window_width, config.window_height

    return {
        "app_name": app_name,
        "organization_name": organization_name,
        "web_app_url": web_app_url,
        "allowed_hosts": sorted(allowed_hosts),
        "allow_subdomains": args.allow_subdomains or config.allow_subdomains,
        "open_external_links": args.open_external_links or config.open_external_links,
        "allow_insecure_http": allow_insecure_http,
        "start_maximized": (not args.not_maximized) and config.start_maximized,
        "window_width": width,
        "window_height": height,
        "persist_session": args.persist_session or config.persist_session,
        "allow_downloads": args.allow_downloads or config.allow_downloads,
        "page_background_color": config.page_background_color,
        "app_icon": "assets/digi_express.icns",
        "single_instance": config.single_instance,
        "show_splash": config.show_splash,
        "splash_duration": config.splash_duration,
        "enable_tray": config.enable_tray,
        "minimize_to_tray": config.minimize_to_tray,
        "default_downloads_path": config.default_downloads_path,
        "show_download_notifications": config.show_download_notifications,
        "user_agent": config.user_agent,
        "browser_locale": config.browser_locale,
        "run_on_startup": config.run_on_startup,
        "allow_file_drop": config.allow_file_drop,
        "wrapper_version": str(args.wrapper_version or "1.0.0").strip(),
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


def resolve_icon(args: argparse.Namespace) -> Path:
    if args.icon is not None:
        icon = args.icon
        if not icon.is_file():
            raise SystemExit(f"Configuration error: icon not found: {icon}")
        if icon.suffix.lower() != ".icns":
            raise SystemExit("Configuration error: macOS icons must be .icns files.")
        return icon
    return generate_icon()


def build_pyinstaller(
    args: argparse.Namespace,
    icon: Path,
    app_name: str,
    bundle_id: str,
    environment: dict[str, str],
) -> None:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--console" if args.debug else "--windowed",
        "--noupx",
        "--optimize",
        "2",
        "--name",
        app_name,
        "--osx-bundle-identifier",
        bundle_id,
        "--target-architecture",
        "universal2",
        "--paths",
        str(PROJECT_ROOT),
        "--hidden-import",
        "webview.platforms.cocoa",
        "--collect-all",
        "webview",
        "--add-data",
        f"{PROJECT_ROOT / 'assets'}:assets",
        "--add-data",
        f"{PROJECT_ROOT / 'app' / 'scripts'}:app/scripts",
        "--exclude-module",
        "PySide6",
        "--exclude-module",
        "PyQt6",
        "--exclude-module",
        "PyQt5",
        "--exclude-module",
        "cefpython3",
        "--exclude-module",
        "gi",
        "--exclude-module",
        "kivy",
        "--onedir" if args.onedir else "--onefile",
    ]
    command.extend(["--icon", str(icon)])
    command.append(str(PROJECT_ROOT / "run.py"))
    run(command, environment=environment)


def build_nuitka(
    args: argparse.Namespace,
    icon: Path,
    app_name: str,
    bundle_id: str,
    wrapper_version: str,
    environment: dict[str, str],
) -> None:
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--show-progress",
        "--remove-output",
        "--disable-plugin=pywebview",
        "--enable-plugin=no-qt",
        "--no-deployment-flag=excluded-module-usage",
        f"--output-dir={PROJECT_ROOT / 'dist'}",
        f"--output-filename={safe_executable_name(app_name)}",
        "--macos-create-app-bundle",
        f"--macos-app-name={app_name}",
        f"--macos-signed-app-name={bundle_id}",
        f"--macos-app-version={wrapper_version}",
        "--include-package=app",
        "--include-package=dotenv",
        "--include-package=webview",
        "--include-module=webview.platforms.cocoa",
        f"--include-data-dir={PROJECT_ROOT / 'assets'}=assets",
        f"--include-data-dir={PROJECT_ROOT / 'app' / 'scripts'}=app/scripts",
        f"--macos-app-icon={icon}",
    ]
    if not args.debug:
        command.append("--macos-disable-console")
    if not args.onedir:
        command.append("--onefile")
    command.append(str(PROJECT_ROOT / "run.py"))
    run(command, environment=environment)


def locate_app_bundle(app_name: str) -> Path:
    dist = PROJECT_ROOT / "dist"
    expected = dist / f"{app_name}.app"
    if expected.is_dir():
        return expected

    candidates = [p for p in dist.glob("*.app") if p.is_dir()]
    if not candidates:
        raise SystemExit(f"No .app bundle was produced in {dist}.")
    source = candidates[0]
    if source != expected:
        shutil.move(str(source), str(expected))
    return expected


def bundle_binary(app_path: Path) -> Path:
    macos_dir = app_path / "Contents" / "MacOS"
    entries = [
        p
        for p in macos_dir.iterdir()
        if p.is_file() and not p.suffix.lower() in {".dylib", ".so", ".a"}
    ]
    if not entries:
        raise SystemExit(f"No executable found in {macos_dir}.")
    return entries[0]


def configure_bundle(app_path: Path, bundle_id: str, wrapper_version: str) -> None:
    plist_path = app_path / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        plist = plistlib.load(handle)
    plist["LSMinimumSystemVersion"] = "12.0"
    plist["CFBundleIdentifier"] = bundle_id
    plist["CFBundleShortVersionString"] = wrapper_version
    plist["CFBundleVersion"] = wrapper_version
    plist["NSHighResolutionCapable"] = True
    with plist_path.open("wb") as handle:
        plistlib.dump(plist, handle)


def remove_quarantine(path: Path) -> None:
    """Remove macOS quarantine and extended attributes from a file or bundle.
    
    The quarantine attribute (com.apple.quarantine) is set by Gatekeeper when a file
    is downloaded from the internet or created from untrusted sources. Removing it
    along with Finder detritus ensures the app bundle, ZIP, and DMG open cleanly without
    Gatekeeper blockers or codesign detritus errors.
    
    Args:
        path: File or directory bundle to remove quarantine from.
    """
    if not path.exists():
        return

    is_dir = path.is_dir()
    target_desc = f"app bundle: {path.name}" if is_dir else path.name
    print(f"Removing quarantine attribute from {target_desc}")

    # Remove com.apple.quarantine attribute specifically
    quarantine_args = ["xattr", "-r", "-d", "com.apple.quarantine", str(path)] if is_dir else ["xattr", "-d", "com.apple.quarantine", str(path)]
    run(quarantine_args, check=False)

    # Clear all extended attributes (detritus, FinderInfo, etc.)
    clear_args = ["xattr", "-c", "-r", str(path)] if is_dir else ["xattr", "-c", str(path)]
    result = run(clear_args, check=False)

    if result.returncode == 0:
        print(f"[OK] Quarantine and extended attributes removed from {path.name}")
    else:
        # Check if com.apple.quarantine is still present
        check_result = run(["xattr", "-p", "com.apple.quarantine", str(path)], check=False)
        if check_result.returncode != 0:
            print(f"[OK] No quarantine attribute found on {path.name} (already clean)")
        else:
            print(f"[WARN] Notice: Could not remove all attributes on {path.name}: {result.stderr.strip() or 'unknown'}")


def sign_bundle(path: Path) -> None:
    remove_quarantine(path)
    run(["codesign", "--force", "--deep", "--sign", "-", "--options", "runtime", str(path)])
    remove_quarantine(path)


def architecture_suffix(builder: str) -> str:
    if builder == "nuitka":
        machine = platform.machine().lower()
        return "arm64" if machine in {"arm64", "aarch64"} else "x86_64"
    return "universal"


def create_distribution(
    app_path: Path,
    app_name: str,
    arch_suffix: str,
    skip_dmg: bool,
) -> tuple[Path, Path]:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    file_stem = safe_executable_name(app_name)
    zip_path = OUTPUT_ROOT / f"{file_stem}-macOS-{arch_suffix}.app.zip"
    dmg_path = OUTPUT_ROOT / f"{file_stem}-macOS-{arch_suffix}.dmg"
    print("Creating distribution packages:")
    print(f"Creating ZIP archive: {zip_path.name}")
    run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app_path), str(zip_path)])
    remove_quarantine(zip_path)
    write_checksum(zip_path)
    if skip_dmg:
        return zip_path, dmg_path

    staging = MACOS_ROOT / "staging" / "dmg"
    staging.mkdir(parents=True, exist_ok=True)
    staged_app = staging / app_path.name
    shutil.copytree(app_path, staged_app)
    remove_quarantine(staged_app)
    (staging / "Applications").symlink_to("/Applications")
    print(f"Creating DMG: {dmg_path.name}")
    run(["hdiutil", "create", "-volname", app_name, "-srcfolder", str(staging), "-ov", "-format", "UDZO", str(dmg_path)])
    print("Code signing and quarantine removal:")
    sign_bundle(dmg_path)
    print()
    write_checksum(dmg_path)
    return zip_path, dmg_path


def main() -> int:
    load_build_environment()
    args = parse_args()
    builder_engine = args.builder.lower()
    validate_environment(builder_engine)
    if builder_engine == "nuitka":
        if importlib.util.find_spec("nuitka") is None and shutil.which("nuitka") is None:
            print(
                "Nuitka is not installed. Run: "
                "python3 -m pip install nuitka zstandard",
                file=sys.stderr,
            )
            return 3

    payload = embedded_payload(args)
    app_name = str(payload["app_name"])
    wrapper_version = str(payload["wrapper_version"] or "1.0.0")
    bundle_id = os.getenv("APP_BUNDLE_ID", DEFAULT_BUNDLE_ID).strip() or DEFAULT_BUNDLE_ID

    clean_previous_builds()
    if not args.skip_quarantine_strip:
        strip_source_quarantine()
    icon = resolve_icon(args)

    original_content = EMBEDDED_CONFIG_PATH.read_text(encoding="utf-8")
    environment = os.environ.copy()
    environment["MACOSX_DEPLOYMENT_TARGET"] = "12.0"
    try:
        write_embedded_config(payload)
        print(f"Building application with {builder_engine.capitalize()}...")
        if builder_engine == "nuitka":
            build_nuitka(args, icon, app_name, bundle_id, wrapper_version, environment)
        else:
            build_pyinstaller(args, icon, app_name, bundle_id, environment)
    finally:
        EMBEDDED_CONFIG_PATH.write_text(original_content, encoding="utf-8")

    app_path = locate_app_bundle(app_name)
    configure_bundle(app_path, bundle_id, wrapper_version)
    print(f"\nCode signing and quarantine removal:")
    sign_bundle(app_path)
    print()
    run(["lipo", "-info", str(bundle_binary(app_path))])
    zip_path, dmg_path = create_distribution(app_path, app_name, architecture_suffix(builder_engine), args.skip_dmg)
    print(f"Build complete: {dmg_path if not args.skip_dmg else zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())