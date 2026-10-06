from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
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

from app.config import AppConfig
from tools.build import (
    normalize_local_url,
    safe_executable_name,
    staged_application,
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
        description="Build a macOS app and development or notarized distribution artifacts."
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
    parser.add_argument(
        "--distribution",
        choices=["development", "direct"],
        default=os.getenv("MACOS_DISTRIBUTION", "development").lower(),
        help="development uses ad-hoc signing; direct uses Developer ID and notarization.",
    )
    parser.add_argument(
        "--signing-identity",
        default=os.getenv("MACOS_SIGNING_IDENTITY", ""),
        help="Developer ID Application identity used by --distribution direct.",
    )
    parser.add_argument(
        "--notary-profile",
        default=os.getenv("MACOS_NOTARY_PROFILE", ""),
        help="Keychain profile created by 'xcrun notarytool store-credentials'.",
    )
    parser.add_argument("--skip-dmg", action="store_true", help="Build the .app and ZIP only.")
    return parser.parse_args()


def run(
    command: list[str],
    *,
    environment: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=False, text=True, capture_output=True)
    if check and result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr)
        raise subprocess.CalledProcessError(result.returncode, command, result.stdout, result.stderr)
    return result


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

    required_modules = ["Cocoa", "Quartz", "Security", "WebKit", "webview"]
    if builder == "pyinstaller":
        required_modules.append("PyInstaller")
    missing_modules = [
        module
        for module in required_modules
        if importlib.util.find_spec(module) is None
    ]
    if missing_modules:
        raise SystemExit(
            "Missing macOS dependencies: "
            + ", ".join(missing_modules)
            + ". Run: "
            "python3 -m pip install -r requirements-macos.txt"
        )

    if builder == "pyinstaller":
        result = subprocess.run(
            ["lipo", "-archs", sys.executable],
            capture_output=True,
            text=True,
            check=False,
        )
        architectures = set(result.stdout.split())
        missing = {"arm64", "x86_64"} - architectures
        if missing:
            raise SystemExit(
                "PyInstaller universal2 requires a Universal2 Python; missing: "
                + ", ".join(sorted(missing))
            )


def validate_direct_distribution(args: argparse.Namespace) -> None:
    """Validate direct-distribution inputs before doing an expensive build."""
    if args.distribution != "direct":
        return
    if args.skip_dmg:
        raise SystemExit("Direct distribution requires a DMG; remove --skip-dmg.")
    if not args.signing_identity.strip():
        raise SystemExit(
            "Direct distribution requires --signing-identity with a "
            "Developer ID Application certificate."
        )
    if "Developer ID Application:" not in args.signing_identity:
        raise SystemExit(
            "The signing identity must be a Developer ID Application certificate."
        )
    if not args.notary_profile.strip():
        raise SystemExit(
            "Direct distribution requires --notary-profile created with "
            "'xcrun notarytool store-credentials'."
        )
    for command in ("xcrun", "spctl", "security"):
        if shutil.which(command) is None:
            raise SystemExit(f"Missing required direct-distribution tool: {command}")

    identity = run(
        ["security", "find-identity", "-v", "-p", "codesigning"],
        check=False,
    )
    if identity.returncode != 0 or args.signing_identity not in identity.stdout:
        raise SystemExit(
            f"Signing identity is not available in the keychain: {args.signing_identity}"
        )


def embedded_payload(args: argparse.Namespace) -> dict[str, object]:
    load_build_environment()
    # Build inputs come from .env/CLI even if an interrupted build left CONFIG populated.
    config = AppConfig.load(packaged=False)

    allow_insecure_http = args.allow_insecure_http or config.allow_insecure_http
    web_app_url = normalize_local_url(args.url or config.web_app_url)
    try:
        primary_host = validate_url(web_app_url, allow_insecure_http)
    except ValueError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

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
        f"ENV_TEXT = {ENV_PATH.read_text(encoding='utf-8')!r}\n"
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
    default_icon = PROJECT_ROOT / "assets" / "digi_express.icns"
    if default_icon.is_file():
        return default_icon
    return generate_icon()


def build_pyinstaller(
    args: argparse.Namespace,
    icon: Path,
    app_name: str,
    bundle_id: str,
    environment: dict[str, str],
    source_root: Path = PROJECT_ROOT,
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
        str(source_root),
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
    command.append(str(source_root / "run.py"))
    run(command, environment=environment)


def build_nuitka(
    args: argparse.Namespace,
    icon: Path,
    app_name: str,
    bundle_id: str,
    wrapper_version: str,
    environment: dict[str, str],
    source_root: Path = PROJECT_ROOT,
) -> None:
    console_mode = "force" if args.debug else "disable"
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
        f"--output-folder-name={safe_executable_name(app_name)}",
        "--macos-create-app-bundle",
        f"--macos-app-name={app_name}",
        f"--macos-signed-app-name={bundle_id}",
        f"--macos-app-version={wrapper_version}",
        f"--macos-app-console-mode={console_mode}",
        "--include-package=app",
        "--include-package=dotenv",
        "--include-package=webview",
        "--include-module=webview.platforms.cocoa",
        f"--include-data-dir={PROJECT_ROOT / 'assets'}=assets",
        f"--include-data-dir={PROJECT_ROOT / 'app' / 'scripts'}=app/scripts",
        f"--macos-app-icon={icon}",
    ]
    command.append(str(source_root / "run.py"))
    run(command, environment=environment)


def locate_app_bundle(app_name: str) -> Path:
    dist = PROJECT_ROOT / "dist"
    expected = dist / f"{app_name}.app"
    if expected.is_dir() and (expected / "Contents" / "Info.plist").is_file():
        return expected

    # Find any .app bundle that contains Info.plist
    candidates = [
        p
        for p in dist.glob("**/*.app")
        if p.is_dir() and (p / "Contents" / "Info.plist").is_file()
    ]
    if not candidates:
        raise SystemExit(f"No valid .app bundle with Contents/Info.plist was produced in {dist}.")
    source = candidates[0]
    if source != expected:
        if expected.exists():
            if expected.is_dir():
                shutil.rmtree(expected)
            else:
                expected.unlink()
        shutil.move(str(source), str(expected))
    return expected


def bundle_binary(app_path: Path) -> Path:
    macos_dir = app_path / "Contents" / "MacOS"
    entries = [
        p
        for p in macos_dir.iterdir()
        if p.is_file() and p.suffix.lower() not in {".dylib", ".so", ".a"}
    ]
    if not entries:
        raise SystemExit(f"No executable found in {macos_dir}.")
    return entries[0]


def validate_bundle_architectures(app_path: Path, builder: str) -> None:
    expected = (
        {"arm64", "x86_64"}
        if builder == "pyinstaller"
        else {architecture_suffix(builder)}
    )
    failures: list[str] = []
    for path in [bundle_binary(app_path), *nested_code_paths(app_path)]:
        if path.is_dir():
            continue
        result = run(["lipo", "-archs", str(path)], check=False)
        if result.returncode != 0:
            continue
        architectures = set(result.stdout.split())
        missing = expected - architectures
        if missing:
            failures.append(f"{path.relative_to(app_path)} missing {', '.join(sorted(missing))}")
    if failures:
        raise SystemExit("Bundle architecture validation failed:\n" + "\n".join(failures))


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


def sign_development_bundle(path: Path) -> None:
    run(["codesign", "--force", "--deep", "--sign", "-", str(path)])


def nested_code_paths(app_path: Path) -> list[Path]:
    """Return signable nested code from deepest path to shallowest path."""
    candidates: set[Path] = set()
    for path in app_path.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_dir() and path.suffix in {".framework", ".app", ".xpc"} or path.is_file() and (
            path.suffix.lower() in {".dylib", ".so"}
            or os.access(path, os.X_OK)
        ) and run(["lipo", "-archs", str(path)], check=False).returncode == 0:
            candidates.add(path)
    candidates.discard(app_path)
    return sorted(candidates, key=lambda value: len(value.parts), reverse=True)


def sign_direct_bundle(app_path: Path, identity: str) -> None:
    """Sign nested code first, then the app with hardened runtime and timestamps."""
    common = [
        "codesign",
        "--force",
        "--options",
        "runtime",
        "--timestamp",
        "--sign",
        identity,
    ]
    for path in nested_code_paths(app_path):
        run([*common, str(path)])
    run([*common, str(app_path)])
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app_path)])


def notarize(path: Path, profile: str, log_name: str, *, staple: bool = True) -> None:
    """Submit an artifact, require acceptance, then staple and validate it."""
    result = run(
        [
            "xcrun",
            "notarytool",
            "submit",
            str(path),
            "--keychain-profile",
            profile,
            "--wait",
            "--output-format",
            "json",
        ],
        check=False,
    )
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = OUTPUT_ROOT / log_name
    log_path.write_text(
        result.stdout + (f"\n{result.stderr}" if result.stderr else ""),
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise SystemExit(f"Notarization command failed; see {log_path}")
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Notarization returned invalid JSON; see {log_path}") from exc
    submission_id = str(response.get("id", "unknown"))
    if response.get("status") != "Accepted":
        if submission_id != "unknown":
            diagnostic = run([
                "xcrun", "notarytool", "log", submission_id,
                "--keychain-profile", profile,
            ], check=False)
            log_path.with_suffix(".diagnostic.json").write_text(
                diagnostic.stdout or diagnostic.stderr, encoding="utf-8"
            )
        raise SystemExit(
            f"Notarization was not accepted (submission {submission_id}); see {log_path}"
        )
    print(f"Notarization accepted: {submission_id}")
    if staple:
        run(["xcrun", "stapler", "staple", str(path)])
        run(["xcrun", "stapler", "validate", str(path)])


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
    distribution: str = "development",
    signing_identity: str = "",
    notary_profile: str = "",
) -> tuple[Path, Path]:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    file_stem = safe_executable_name(app_name)
    zip_path = OUTPUT_ROOT / f"{file_stem}-macOS-{arch_suffix}.app.zip"
    dmg_path = OUTPUT_ROOT / f"{file_stem}-macOS-{arch_suffix}.dmg"
    print("Creating distribution packages:")
    if skip_dmg:
        print(f"Creating ZIP archive: {zip_path.name}")
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app_path), str(zip_path)])
        write_checksum(zip_path)
        return zip_path, dmg_path

    staging = MACOS_ROOT / "staging" / "dmg"
    staging.mkdir(parents=True, exist_ok=True)
    staged_app = staging / app_path.name
    shutil.copytree(app_path, staged_app, symlinks=True)
    (staging / "Applications").symlink_to("/Applications")
    print(f"Creating DMG: {dmg_path.name}")
    run(["hdiutil", "create", "-volname", app_name, "-srcfolder", str(staging), "-ov", "-format", "UDZO", str(dmg_path)])
    if distribution == "direct":
        run(
            [
                "codesign",
                "--force",
                "--timestamp",
                "--sign",
                signing_identity,
                str(dmg_path),
            ]
        )
        run(["codesign", "--verify", "--verbose=2", str(dmg_path)])
        notarize(dmg_path, notary_profile, "notarization-dmg.json")
        run(["spctl", "--assess", "--type", "open", "--context", "context:primary-signature", "--verbose=2", str(dmg_path)])
    print(f"Creating ZIP archive: {zip_path.name}")
    run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app_path), str(zip_path)])
    write_checksum(zip_path)
    write_checksum(dmg_path)
    return zip_path, dmg_path


def main() -> int:
    load_build_environment()
    args = parse_args()
    builder_engine = args.builder.lower()
    validate_environment(builder_engine)
    validate_direct_distribution(args)
    if args.distribution == "direct":
        args.onedir = True
    if (builder_engine == "nuitka" and importlib.util.find_spec("nuitka") is None
        and shutil.which("nuitka") is None):
        print(
            "Nuitka is not installed. Run: python3 -m pip install nuitka zstandard",
            file=sys.stderr,
        )
        return 3

    payload = embedded_payload(args)
    app_name = str(payload["app_name"])
    wrapper_version = str(payload["wrapper_version"] or "1.0.0")
    print(f"Embedding wrapper version {wrapper_version} (builder: {builder_engine}).")
    bundle_id = os.getenv("APP_BUNDLE_ID", DEFAULT_BUNDLE_ID).strip() or DEFAULT_BUNDLE_ID

    clean_previous_builds()
    icon = resolve_icon(args)

    environment = os.environ.copy()
    environment["MACOSX_DEPLOYMENT_TARGET"] = "12.0"
    with staged_application(PROJECT_ROOT, payload) as source_root:
        print(f"Building application with {builder_engine.capitalize()}...")
        if builder_engine == "nuitka":
            build_nuitka(args, icon, app_name, bundle_id, wrapper_version, environment, source_root)
        else:
            build_pyinstaller(args, icon, app_name, bundle_id, environment, source_root)

    app_path = locate_app_bundle(app_name)
    configure_bundle(app_path, bundle_id, wrapper_version)
    validate_bundle_architectures(app_path, builder_engine)
    if args.distribution == "direct":
        sign_direct_bundle(app_path, args.signing_identity)
        app_archive = OUTPUT_ROOT / f"{safe_executable_name(app_name)}-notarization.zip"
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        run(["ditto", "-c", "-k", "--keepParent", str(app_path), str(app_archive)])
        notarize(
            app_archive,
            args.notary_profile,
            "notarization-app.json",
            staple=False,
        )
        # ZIP tickets cannot be stapled; staple and validate the enclosed app.
        run(["xcrun", "stapler", "staple", str(app_path)])
        run(["xcrun", "stapler", "validate", str(app_path)])
        run(["spctl", "--assess", "--type", "execute", "--verbose=2", str(app_path)])
    else:
        sign_development_bundle(app_path)
    run(["lipo", "-info", str(bundle_binary(app_path))])
    zip_path, dmg_path = create_distribution(
        app_path,
        app_name,
        architecture_suffix(builder_engine),
        args.skip_dmg,
        args.distribution,
        args.signing_identity,
        args.notary_profile,
    )
    print(f"Build complete: {dmg_path if not args.skip_dmg else zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
