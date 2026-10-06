from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EMBEDDED_CONFIG_PATH = PROJECT_ROOT / "app" / "embedded_config.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a hardened single-executable desktop wrapper with the "
            "build-time configuration embedded as plain values."
        )
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
        help="Build a directory package instead of the default single executable.",
    )
    parser.add_argument(
        "--icon",
        type=Path,
        help="Optional platform-compatible application icon.",
    )
    parser.add_argument(
        "--builder",
        choices=["pyinstaller", "nuitka"],
        default=os.getenv("BUILDER_ENGINE", "pyinstaller").lower(),
        help="Compilation engine: pyinstaller (default) or nuitka (native C++ compilation).",
    )
    parser.add_argument(
        "--wrapper-version",
        default=os.getenv("APP_WRAPPER_VERSION", os.getenv("WRAPPER_VERSION", "1.0.0")),
        help="Desktop wrapper version sent in the 'X-Wrapper-Version' request header (default: 1.0.0).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Keep console window enabled to view stdout/stderr and tracebacks.",
    )
    return parser.parse_args()


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def normalize_local_url(url: str) -> str:
    normalized = url.strip()
    if re.fullmatch(
        r"(localhost|127\.0\.0\.1|\[::1\])(:\d{1,5})?(/.*)?",
        normalized,
        flags=re.IGNORECASE,
    ):
        return f"http://{normalized}"
    return normalized


def validate_url(url: str, allow_insecure_http: bool) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("The URL must be a valid HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("Do not embed credentials in the application URL.")
    if parsed.query or parsed.fragment:
        raise ValueError(
            "The initial URL must not contain a query string or fragment. "
            "Never place access tokens or secrets in a URL."
        )

    is_localhost = parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not is_localhost and not allow_insecure_http:
        raise ValueError("Remote applications must use HTTPS.")

    return parsed.hostname.lower().rstrip(".")


def safe_executable_name(name: str) -> str:
    normalized = re.sub(r'[<>:"/\\|?*]+', "-", name).strip().strip(".")
    if not normalized:
        raise ValueError("The application name must contain a valid character.")
    return normalized


def write_embedded_config(payload: dict) -> None:
    """Write the build-time configuration into embedded_config.py as plain values."""
    # repr() emits real Python literals (True/False/None), not JSON's lowercase
    # true/false/null, so the generated module imports cleanly.
    rendered = repr(payload)
    content = (
        '"""Generated temporarily by tools/build.py."""\n\n'
        f"ENV_TEXT = {(PROJECT_ROOT / '.env').read_text(encoding='utf-8')!r}\n"
        f"CONFIG = {rendered}\n"
    )
    EMBEDDED_CONFIG_PATH.write_text(content, encoding="utf-8")


@contextmanager
def staged_application(project_root: Path, payload: dict) -> Iterator[Path]:
    """Compile an isolated source copy; never overwrite repository configuration."""
    with TemporaryDirectory(prefix="webdesktop-build-") as directory:
        source_root = Path(directory)
        shutil.copytree(project_root / "app", source_root / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy2(project_root / "run.py", source_root / "run.py")
        environment_text = (project_root / ".env").read_text(encoding="utf-8")
        (source_root / "app" / "embedded_config.py").write_text(
            '"""Build-generated configuration, including the complete environment."""\n\n'
            f"ENV_TEXT = {environment_text!r}\nCONFIG = {payload!r}\n", encoding="utf-8"
        )
        yield source_root


def executable_output_path(name: str, onedir: bool) -> Path:
    if onedir:
        return PROJECT_ROOT / "dist" / name
    suffix = ".exe" if os.name == "nt" else ""
    return PROJECT_ROOT / "dist" / f"{name}{suffix}"


def remove_previous_output(name: str, onedir: bool) -> None:
    """Delete the previous build artifact (file or directory) and its checksum."""
    output = executable_output_path(name, onedir)
    checksum = output.with_suffix(output.suffix + ".sha256")
    for path in (output, checksum):
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink(missing_ok=True)
        except OSError as exc:
            print(f"Warning: could not remove {path}: {exc}", file=sys.stderr)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build() -> int:
    if os.name != "nt":
        print(
            "Build error: the Edge WebView2 executable must be built on Windows.",
            file=sys.stderr,
        )
        return 4

    load_dotenv(PROJECT_ROOT / ".env", override=True)
    args = parse_args()

    web_app_url = normalize_local_url(
        args.url or os.getenv("WEB_APP_URL") or ""
    )
    app_name = (
        args.name or os.getenv("APP_NAME") or "Web Desktop"
    ).strip()
    organization_name = (
        args.organization
        or os.getenv("APP_ORGANIZATION")
        or "WebDesktop"
    ).strip()

    try:
        allow_insecure_http = args.allow_insecure_http or parse_bool(
            os.getenv("ALLOW_INSECURE_HTTP"),
            False,
        )
        allow_subdomains = args.allow_subdomains or parse_bool(
            os.getenv("ALLOW_SUBDOMAINS"),
            False,
        )
        open_external_links = args.open_external_links or parse_bool(
            os.getenv("OPEN_EXTERNAL_LINKS"),
            False,
        )
        persist_session = args.persist_session or parse_bool(
            os.getenv("PERSIST_SESSION"),
            False,
        )
        allow_downloads = args.allow_downloads or parse_bool(
            os.getenv("ALLOW_DOWNLOADS"),
            False,
        )
        start_maximized = not args.not_maximized and parse_bool(
            os.getenv("START_MAXIMIZED"),
            True,
        )
        page_background_color = (
            os.getenv("PAGE_BACKGROUND_COLOR", "#ffffff").strip().lower()
        )
        if not re.fullmatch(r"#[0-9a-f]{6}", page_background_color):
            raise ValueError(
                "PAGE_BACKGROUND_COLOR must use the #RRGGBB format."
            )
        primary_host = validate_url(web_app_url, allow_insecure_http)
        executable_name = safe_executable_name(app_name)
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.windowed_size is not None:
        width, height = args.windowed_size
    else:
        try:
            width = int(os.getenv("WINDOW_WIDTH", "1280"))
            height = int(os.getenv("WINDOW_HEIGHT", "800"))
        except ValueError:
            print(
                "Configuration error: WINDOW_WIDTH and WINDOW_HEIGHT must be integers.",
                file=sys.stderr,
            )
            return 2

    if not (800 <= width <= 7680 and 600 <= height <= 4320):
        print(
            "Configuration error: width must be 800-7680 and height 600-4320.",
            file=sys.stderr,
        )
        return 2

    # Auto-generate multi-resolution ICO from portrait/landscape assets if Pillow is installed
    default_ico = PROJECT_ROOT / "assets" / "digi_express.ico"
    portrait_jpg = PROJECT_ROOT / "assets" / "digi_portrait.jpg"
    landscape_jpg = PROJECT_ROOT / "assets" / "digi_landscape.jpg"

    source_img_path = portrait_jpg if portrait_jpg.is_file() else (landscape_jpg if landscape_jpg.is_file() else None)
    if source_img_path and importlib.util.find_spec("PIL") is not None:
        try:
            from PIL import Image
            src_img = Image.open(source_img_path)
            if src_img.mode != "RGBA":
                src_img = src_img.convert("RGBA")
            w, h = src_img.size
            min_dim = min(w, h)
            left = (w - min_dim) // 2
            top = (h - min_dim) // 2
            sq_img = src_img.crop((left, top, left + min_dim, top + min_dim))
            ico_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
            resample_filter = getattr(getattr(Image, "Resampling", None), "LANCZOS", None)
            if resample_filter is None:
                resample_filter = getattr(Image, "LANCZOS", None)
            if resample_filter is None:
                raise AttributeError("Pillow does not expose a supported LANCZOS resampling filter")
            icons = [sq_img.resize(size, resample_filter) for size in ico_sizes]
            icons[0].save(str(default_ico), format="ICO", sizes=ico_sizes, append_images=icons[1:])
            print(f"Generated multi-resolution ICO from {source_img_path.name}: {default_ico}")
        except Exception as exc:
            print(f"Warning: Failed to generate ICO from asset: {exc}", file=sys.stderr)

    icon_path = args.icon if args.icon is not None else default_ico
    if icon_path is not None and not icon_path.is_file():
        if args.icon is not None:
            print(f"Configuration error: icon not found: {args.icon}", file=sys.stderr)
            return 2
        icon_path = None

    builder_engine = args.builder.lower()
    if builder_engine == "pyinstaller":
        if importlib.util.find_spec("PyInstaller") is None:
            print(
                "PyInstaller is not installed. Run: "
                "python -m pip install -r requirements.txt",
                file=sys.stderr,
            )
            return 3
    elif (builder_engine == "nuitka" and importlib.util.find_spec("nuitka") is None
          and shutil.which("nuitka") is None):
        print(
            "Nuitka is not installed. Run: python -m pip install nuitka zstandard",
            file=sys.stderr,
        )
        return 3

    env_hosts = [
        host.strip().lower().rstrip(".")
        for host in os.getenv("WEB_APP_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    ]
    allowed_hosts = {
        primary_host,
        *env_hosts,
        *(
            host.strip().lower().rstrip(".")
            for host in args.allowed_host
            if host.strip()
        ),
    }

    payload = {
        "app_name": app_name,
        "organization_name": organization_name,
        "web_app_url": web_app_url,
        "allowed_hosts": sorted(allowed_hosts),
        "allow_subdomains": allow_subdomains,
        "open_external_links": open_external_links,
        "allow_insecure_http": allow_insecure_http,
        "start_maximized": start_maximized,
        "window_width": width,
        "window_height": height,
        "persist_session": persist_session,
        "allow_downloads": allow_downloads,
        "page_background_color": page_background_color,
        "single_instance": parse_bool(os.getenv("SINGLE_INSTANCE"), True),
        "show_splash": parse_bool(os.getenv("SHOW_SPLASH"), True),
        "splash_duration": float(os.getenv("SPLASH_DURATION", "4.5")),
        "enable_tray": parse_bool(os.getenv("ENABLE_SYSTEM_TRAY"), True),
        "minimize_to_tray": parse_bool(os.getenv("MINIMIZE_TO_TRAY"), False),
        "default_downloads_path": os.getenv("DEFAULT_DOWNLOADS_PATH", "").strip(),
        "show_download_notifications": parse_bool(os.getenv("SHOW_DOWNLOAD_NOTIFICATIONS"), True),
        "user_agent": os.getenv("USER_AGENT", "").strip(),
        "browser_locale": os.getenv("BROWSER_LOCALE", "").strip(),
        "run_on_startup": parse_bool(os.getenv("RUN_ON_STARTUP"), False),
        "allow_file_drop": parse_bool(os.getenv("ALLOW_FILE_DROP"), False),
        "wrapper_version": str(args.wrapper_version or "1.0.0").strip(),
    }
    staging = ExitStack()
    try:
        source_root = staging.enter_context(staged_application(PROJECT_ROOT, payload))

        if builder_engine == "nuitka":
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
                f"--output-filename={executable_name}.exe" if sys.platform == "win32" else f"--output-filename={executable_name}",
                "--include-package=app",
                "--include-package=dotenv",
                "--include-package=webview",
                f"--include-data-dir={PROJECT_ROOT / 'assets'}=assets",
                f"--include-data-dir={PROJECT_ROOT / 'app' / 'scripts'}=app/scripts",
            ]
            if sys.platform == "win32":
                command.extend([
                    "--include-module=webview.platforms.winforms",
                    "--include-module=webview.platforms.edgechromium",
                    "--include-module=webview.platforms.win32",
                    "--include-package=clr_loader",
                    "--include-package=pythonnet",
                    f"--windows-console-mode={'force' if args.debug else 'disable'}",
                ])
                if icon_path is not None:
                    command.append(f"--windows-icon-from-ico={icon_path.resolve()}")
            elif sys.platform == "darwin":
                command.extend([
                    "--include-module=webview.platforms.cocoa",
                ])
                command.append("--macos-create-app-bundle")
                if icon_path is not None:
                    command.append(f"--macos-app-icon={icon_path.resolve()}")

            if not args.onedir:
                command.append("--onefile")

            command.append(str(source_root / "run.py"))
        else:
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
                executable_name,
                "--paths",
                str(source_root),
                "--hidden-import",
                "webview.platforms.edgechromium",
                "--hidden-import",
                "clr",
                "--hidden-import",
                "pythonnet",
                "--hidden-import",
                "clr_loader",
                "--collect-all",
                "webview",
                "--add-data",
                "assets;assets" if sys.platform == "win32" else "assets:assets",
                "--add-data",
                "app/scripts;app/scripts" if sys.platform == "win32" else "app/scripts:app/scripts",
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

            if icon_path is not None:
                command.extend(["--icon", str(icon_path.resolve())])

            command.append(str(source_root / "run.py"))

        remove_previous_output(executable_name, args.onedir)
        print(f"Building application with {builder_engine.capitalize()}...")
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Build failed with exit code {exc.returncode}.", file=sys.stderr)
        return exc.returncode or 1
    finally:
        staging.close()

    output = executable_output_path(executable_name, args.onedir)
    print(f"Build completed: {output}")

    if output.is_file():
        checksum = sha256_file(output)
        checksum_path = output.with_suffix(output.suffix + ".sha256")
        checksum_path.write_text(f"{checksum}  {output.name}\n", encoding="utf-8")
        print(f"SHA-256: {checksum}")
        print(f"Checksum file: {checksum_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(build())
