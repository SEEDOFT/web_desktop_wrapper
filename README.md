# Native Desktop Wrapper (Windows & macOS)

A native desktop wrapper for modern web applications powered by **Microsoft Edge WebView2** on Windows and **Apple Cocoa WKWebView** on macOS.

---

## Table of Contents

- [Features](#features)
- [System Requirements](#system-requirements)
- [Quick Start](#quick-start)
- [Configuration (.env)](#configuration-env)
- [Build Commands \& Guide](#build-commands--guide)
  - [0. Prerequisites (Both Platforms)](#0-prerequisites-both-platforms)
  - [1. Build Windows Standalone Executable (.exe)](#1-build-windows-standalone-executable-exe)
  - [2. Build Windows Offline Installer (Setup.exe)](#2-build-windows-offline-installer-setupexe)
  - [3. Build macOS Universal App \& DMG (.app / .dmg / .zip)](#3-build-macos-universal-app--dmg-app--dmg--zip)
- [Build Engines: PyInstaller vs Nuitka](#build-engines-pyinstaller-vs-nuitka)
- [X-Wrapper-Version Header](#x-wrapper-version-header)
- [JavaScript Scripts Architecture](#javascript-scripts-architecture)
- [Testing \& Static Analysis](#testing--static-analysis)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Gatekeeper \& Quarantine Guide (macOS)](#gatekeeper--quarantine-guide-macos)
- [Performance \& Security](#performance--security)

---

## Features

- **Windows Native**: Uses Microsoft Edge WebView2 (`edgechromium`) via `pywebview`.
- **macOS Native**: Uses Cocoa WKWebView (`wkwebview`) with Universal2 binary support (`arm64` + `x86_64`).
- **Smooth Startup**: Opens the native window only after the first DOM-ready frame; per-monitor DPI aware.
- **Isolated Storage**: Dedicated profile directories for cookies, cache, and session persistence.
- **Hardened Security**: Navigation policies, host allowlists, subdomain controls, DevTools suppression, and custom branded error pages.
- **Automated Quarantine Stripping**: Automatically cleans `com.apple.quarantine` and Finder metadata from built macOS apps, DMGs, and ZIP archives.
- **X-Wrapper-Version Header**: Automatically injects an `X-Wrapper-Version` HTTP request header on every network request, enabling the backend to identify and validate the desktop wrapper version.
- **Dual Build Engines**: Supports both **PyInstaller** (fast packaging) and **Nuitka** (native C++ compilation for maximum reverse-engineering defense).
- **External JavaScript Scripts**: All injected browser scripts are standalone `.js` files in `app/scripts/` with full IDE linting, syntax highlighting, and error detection support.

---

## System Requirements

- **Windows**: Windows 10 / 11 (x64 or x86) with [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/).
- **macOS**: macOS 12 Monterey or later (Apple Silicon & Intel).
- **Python**: Python 3.10+ (Universal2 build required on macOS).

---

## Quick Start

### 1. Environment Setup

#### Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

#### macOS (Terminal):
```bash
python3 -m venv .venv
source .venv/bin/activate

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-macos.txt
```

> **Note**: Do not install PySide6, PyQt, or CEF in this environment to ensure the build collects only native components.

### 2. Development Mode

1. Copy `.env.example` to `.env` and configure your web application:
   ```bash
   cp .env.example .env
   ```
2. Start your local web server (e.g., `http://127.0.0.1:8000`).
3. Run the desktop wrapper:
   ```powershell
   # Windows
   python -m app
   ```
   ```bash
   # macOS
   python3 -m app
   ```

---

## Configuration (.env)

| Variable                      | Default              | Description                                                                           |
| :---------------------------- | :------------------- | :------------------------------------------------------------------------------------ |
| `WEB_APP_URL`                 | *Required*           | Main web application URL (e.g., `https://app.company.com` or `http://127.0.0.1:8000`) |
| `APP_NAME`                    | `DIGI Express Admin` | Window title and application name                                                     |
| `APP_ORGANIZATION`            | `DIGI EXPRESS`       | Organization name for storage directories                                             |
| `ALLOWED_HOSTS`               | Derived from URL     | Comma-separated list of additional trusted hostnames                                  |
| `ALLOW_SUBDOMAINS`            | `false`              | Allow navigation to subdomains of allowed hosts                                       |
| `OPEN_EXTERNAL_LINKS`         | `false`              | Open unlisted URLs in the default system browser                                      |
| `ALLOW_INSECURE_HTTP`         | `false`              | Allow HTTP on non-localhost addresses (production should use HTTPS)                   |
| `PERSIST_SESSION`             | `false`              | Persist cookies and local storage across app restarts                                 |
| `ALLOW_DOWNLOADS`             | `false`              | Enable file downloads                                                                 |
| `START_MAXIMIZED`             | `false`              | Launch window maximized                                                               |
| `SINGLE_INSTANCE`             | `true`               | Prevent duplicate windows and focus existing active instance                          |
| `SHOW_SPLASH`                 | `true`               | Full-window animated splash screen on launch (cinematic dissolve)                    |
| `SPLASH_DURATION`             | `4.5`                | Splash breathing animation hold (seconds); 1.4 s CSS dissolve plays after this       |
| `WINDOW_WIDTH`                | `1280`               | Initial window width in pixels                                                        |
| `WINDOW_HEIGHT`               | `800`                | Initial window height in pixels                                                       |
| `PAGE_BACKGROUND_COLOR`       | `#ffffff`            | Hex background color shown before web page loads                                      |
| `ENABLE_SYSTEM_TRAY`          | `true`               | Enable system tray icon with Open, Reload, and Exit menu                              |
| `MINIMIZE_TO_TRAY`            | `false`              | Hide application to system tray when closed or minimized                             |
| `DEFAULT_DOWNLOADS_PATH`      | *System default*     | Custom folder path for downloaded files                                               |
| `SHOW_DOWNLOAD_NOTIFICATIONS` | `true`               | Display native notification toasts when file downloads complete                       |
| `USER_AGENT`                  | *Default*            | Custom User-Agent header string                                                       |
| `BROWSER_LOCALE`              | *System default*     | Enforced browser language and Accept-Language (e.g. `en-US`, `th-TH`, `vi-VN`)       |
| `RUN_ON_STARTUP`              | `false`              | Launch application automatically on system startup / login                            |
| `ALLOW_FILE_DROP`             | `false`              | Permit dragging and dropping external local files to navigate the browser window      |
| `APP_WRAPPER_VERSION`         | `1.0.0`              | Wrapper version sent in the `X-Wrapper-Version` HTTP request header on every request  |
| `EMBED_WEBVIEW2_RUNTIME`      | `true`               | Embed offline WebView2 runtimes in Windows Setup.exe (`true`) or omit for lightweight installer (`false`) |
| `BUILDER_ENGINE`              | `pyinstaller`        | Compilation engine: `pyinstaller` (default) or `nuitka` (native C++ compilation)      |

---

## Build Commands & Guide

This guide walks you through everything needed to build the desktop wrapper, from downloading Python to the finished artifact, on both **Windows** and **macOS**. A web application (or local dev server) must be reachable at the URL you configure — the wrapper itself is just the native shell around it.

---

### 0. Prerequisites (Both Platforms)

| Requirement | Windows | macOS |
|---|---|---|
| Python 3.10+ (64-bit; **Universal2** on macOS) | `python.org` installer | `python.org` Universal2 installer |
| Native build toolchain | Optional for Nuitka (auto-downloaded MinGW64) | Xcode Command Line Tools (`xcode-select --install`) |
| Git | `git` CLI | `git` CLI |

1. Clone or download this repository:
   ```bash
   git clone <repository-url>
   cd web_desktop_wrapper
   ```

#### Sharing the source (optional)

To send a clean source snapshot to someone else (no `.venv`, build artifacts, downloads, or your `.env`), run the cross-platform cleanup script — works on **Windows** and **macOS** (PowerShell / pwsh):

```powershell
# Remove all generated deps/builds, then create a source .zip next to the folder
powershell -ExecutionPolicy Bypass -File tools/cleanup.ps1

# Clean only, without creating the ZIP
powershell -ExecutionPolicy Bypass -File tools/cleanup.ps1 -SkipZip

# Clean and write the ZIP to a specific directory
powershell -ExecutionPolicy Bypass -File tools/cleanup.ps1 -OutputDir D:\shares
```

```bash
# macOS
pwsh -File tools/cleanup.ps1
```

The script removes `.venv`, `.build-tools`, `build/`, `dist/`, installer and macOS outputs, offline WebView2 downloads, `__pycache__`, `.icns`, `.spec`, `.DS_Store`, and your `.env` (the recipient must copy `.env.example` → `.env`). The zip excludes the `.git` folder. Source-only project size is ~0.3 MB.

---

### 1. Build Windows Standalone Executable (.exe)

#### Step 1.1 — Download & install Python (64-bit)
1. Download the latest **64-bit** Python 3.10+ installer from <https://www.python.org/downloads/windows/>.
2. Run the installer.
3. **Important:** Check **"Add python.exe to PATH"** at the bottom of the first screen, then click **Install Now**.
4. Open **PowerShell** and verify:
   ```powershell
   python --version
   ```
   Expected: `Python 3.10.x` or newer. If `python` is not recognized, restart PowerShell after the install.

#### Step 1.2 — Create and activate the virtual environment
```powershell
cd web_desktop_wrapper
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> If PowerShell blocks script execution, run once: `Set-ExecutionPolicy -Scope Process RemoteSigned`.

#### Step 1.3 — Install build dependencies
```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> **Note**: Do not install PySide6, PyQt, or CEF in this environment to ensure the build collects only native components. `nuitka` is included in `requirements.txt`; on its first Windows build it can auto-download and use MinGW64 as the C compiler.

#### Step 1.4 — Configure the application
```powershell
Copy-Item .env.example .env
```
Edit `.env` and set at minimum `WEB_APP_URL` (and optionally `APP_NAME`, `APP_ORGANIZATION`, security options — see [Configuration (.env)](#configuration-env)).

Sanity-check the development run (optional, but recommended before the first build):
```powershell
python -m app
```
Close the window (or press `Ctrl+W`) when done.

#### Step 1.5 — Build the executable
```powershell
# PyInstaller (default — fast build, bytecode packaging)
python tools/build.py

# Nuitka (native C++ compilation — slower build, maximum reverse-engineering defense)
python tools/build.py --builder nuitka
```
The script embeds the `.env` configuration into the binary, builds, and writes a SHA-256 checksum. The first Nuitka build takes 5–15 minutes; later builds reuse the compiler cache.

#### Step 1.6 — Custom build options
```powershell
# Specify a custom starting URL and allow specific auth hosts
python tools/build.py `
  --url "https://app.company.com" `
  --allowed-host "login.company.com" `
  --allow-subdomains

# Set custom wrapper version (sent as X-Wrapper-Version header)
python tools/build.py --wrapper-version "2.1.0"

# Build a directory package instead of a single executable
python tools/build.py --onedir

# Debug build (keeps the console window visible for troubleshooting)
python tools/build.py --builder nuitka --debug

# Build with a custom icon (Windows uses .ico)
python tools/build.py --icon "assets\digi_express.ico"
```

#### Step 1.7 — Verify the build outputs
- `dist/DIGI Express Admin.exe` — the standalone executable
- `dist/DIGI Express Admin.exe.sha256` — checksum
Double-click the `.exe` or run `.\dist\"DIGI Express Admin.exe"` from PowerShell.

---

### 2. Build Windows Offline Installer (Setup.exe)

Builds a dual-architecture (x86 + x64) installer using **Inno Setup 6**. By default it bundles offline Evergreen WebView2 runtimes and automatically installs the appropriate architecture.

> **Note**: This requires both a 64-bit and a 32-bit Python, and must be run from the 64-bit environment (steps 1.1–1.3 above).

#### Step 2.1 — Install the 32-bit Python (for the x86 build)
1. Download the **32-bit** Python 3.10+ installer from <https://www.python.org/downloads/windows/>.
2. Run the installer and select **Customize installation**.
3. In the *Advanced Options* screen, change the install location to:
   ```
   C:\Python Projects\web_desktop_wrapper\.build-tools\python-x86
   ```
   (adjust to your project path), keep **Add Python to PATH** unchecked (the build invokes it by full path).
4. Install its build dependencies into that interpreter:
   ```powershell
   .\.build-tools\python-x86\python.exe -m pip install --upgrade pip
   .\.build-tools\python-x86\python.exe -m pip install -r requirements.txt
   ```
   > Alternatively, install 32-bit Python anywhere and pass its path each time: `--x86-python "C:\Python311-32\python.exe"`.
5. Verify it is 32-bit:
   ```powershell
   .\.build-tools\python-x86\python.exe -c "import struct; print(struct.calcsize('P')*8)"
   ```
   Expected output: `32`.

#### Step 2.2 — Install Inno Setup 6
1. Download and install [Inno Setup 6](https://jrsoftware.org/isdl.php) (default location: `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`).

#### Step 2.3 — Download the offline WebView2 runtimes
1. From <https://developer.microsoft.com/en-us/microsoft-edge/webview2/> download the **Evergreen Standalone (offline) installers** for both architectures.
2. Place them with these exact filenames:
   - `installer/downloads/MicrosoftEdgeWebView2RuntimeInstallerX64.exe`
   - `installer/downloads/MicrosoftEdgeWebView2RuntimeInstallerX86.exe`
3. Skip this step entirely if you plan to build a lightweight installer with `--no-embed-runtime` (see Step 2.5).

#### Step 2.4 — Configure the application
Follow Step 1.4 above (`.env` must already exist and be configured).

#### Step 2.5 — Build the installer
```powershell
# Standard offline installer (bundles offline WebView2 runtimes, ~300MB)
python tools/build_installer.py

# Lightweight installer without embedded offline WebView2 runtimes
python tools/build_installer.py --no-embed-runtime

# Build installer using Nuitka native C++ compilation
python tools/build_installer.py --builder nuitka
```

#### Step 2.6 — Custom toolchain options
```powershell
python tools/build_installer.py `
  --x64-python "C:\Python311\python.exe" `
  --x86-python "C:\Python311-32\python.exe" `
  --iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" `
  --wrapper-version "2.1.0" `
  --debug
```

#### Step 2.7 — Verify the build outputs
- `installer/output/DIGI-Express-Admin-Setup.exe` — the dual-architecture installer
- `installer/output/DIGI-Express-Admin-Setup.exe.sha256`
- `dist/DIGI Express Admin.exe` is also refreshed with the x64 build and a new checksum.

---

### 3. Build macOS Universal App & DMG (.app / .dmg / .zip)

Builds a universal macOS application (`arm64` + `x86_64`), signs it with hardened runtime (ad-hoc), automatically strips quarantine/extended attributes from the project and toolchain, and creates ZIP + DMG distribution packages.

> **Note**: Must be run on macOS (macOS 12 Monterey or later).

#### Empty Mac: shortest complete build path

Run the first two commands in Terminal, install the **Universal2** Python `.pkg` from the page that opens, then return to Terminal and run the remaining commands. Replace `/path/to/web_desktop_wrapper` with the folder you copied or cloned onto the Mac.

```bash
# 1. Install Apple's command-line build tools and open the official Python installer page
xcode-select --install
open "https://www.python.org/downloads/macos/"

# 2. After installing the Universal2 Python package, build the project
cd "/path/to/web_desktop_wrapper"
lipo -archs "$(command -v python3)"       # must show both: arm64 x86_64
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-macos.txt
cp -n .env.example .env
open -e .env                              # set WEB_APP_URL, save, then close TextEdit
python3 tools/build_macos.py
open macos/output
```

The final DMG, ZIP, and SHA-256 files are in `macos/output/`. On later builds, start with `cd`, activate `.venv`, and run `python3 tools/build_macos.py` again.

#### Step 3.1 — Install Universal2 Python
1. Download the **Universal2** macOS installer for Python 3.10+ from <https://www.python.org/downloads/macos/> (the package name contains "Universal2").
2. Run the `.pkg` installer.
3. **Do not use Homebrew Python for building**: it is single-architecture and the build requires a Universal2 interpreter.
4. Verify it contains both architectures:
   ```bash
   lipo -archs "$(command -v python3)"
   ```
   Expected output: `arm64 x86_64`. Also confirm the version:
   ```bash
   python3 --version
   ```

#### Step 3.2 — Install Xcode Command Line Tools (for Nuitka & code signing)
```bash
xcode-select --install
```
Accept the license when prompted: `sudo xcodebuild -license accept`.

#### Step 3.3 — Create and activate the virtual environment
```bash
cd web_desktop_wrapper
python3 -m venv .venv
source .venv/bin/activate
```

#### Step 3.4 — Install build dependencies
```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-macos.txt
```
This installs the shared requirements (`requirements.txt`) plus the `pyobjc` frameworks needed for the native Cocoa WKWebView build.

> **Note**: Do not install PySide6, PyQt, or CEF in this environment to ensure the build collects only native components.

#### Step 3.5 — Configure the application
```bash
cp .env.example .env
```
Edit `.env` and set at minimum `WEB_APP_URL` (and optionally `APP_NAME`, `APP_ORGANIZATION`, security options — see [Configuration (.env)](#configuration-env)).

Sanity-check the development run (optional, but recommended):
```bash
python3 -m app
```
Quit with `Cmd+Q` when done.

#### Step 3.6 — Build the Universal .app, ZIP, and DMG
```bash
# PyInstaller (default — universal2 build, ~30–90 s)
python3 tools/build_macos.py

# Build .app and .zip only (skip DMG creation)
python3 tools/build_macos.py --skip-dmg
```
The script:
1. Loads `.env` before resolving build defaults, validates its settings, and writes the supported runtime values temporarily to `app/embedded_config.py`.
2. Strips `com.apple.quarantine` and extended attributes from the project tree and toolchain (Python, `lipo`, `iconutil`, `hdiutil`, `ditto`, `codesign`, `sips`) so downloaded files never trip Gatekeeper mid-build.
3. Generates a multi-resolution `.icns` from `assets/digi_portrait.jpg` (or landscape fallback).
4. Compiles the `.app`, patches `Info.plist`, ad-hoc signs with hardened runtime, and removes quarantine.
5. Creates the ZIP (always) and DMG (unless `--skip-dmg`) with checksums.

The raw `.env` file is deliberately **not** copied into the application bundle. Its supported application settings are embedded in generated Python configuration, so the built app works without `.env` while avoiding distribution of unrelated environment entries. The generated source file is restored after every build, including failed builds.

#### Step 3.7 — Custom build options
```bash
# Nuitka native C++ compilation (host architecture only: arm64 or x86_64)
python3 tools/build_macos.py --builder nuitka

# Debug build (keeps the console visible for troubleshooting)
python3 tools/build_macos.py --builder nuitka --debug

# Build a directory bundle instead of the default single-file .app
python3 tools/build_macos.py --onedir

# Specify a custom starting URL, app name, and allow specific auth hosts
python3 tools/build_macos.py \
  --url "https://app.company.com" \
  --name "DIGI Express Admin" \
  --allowed-host "login.company.com" \
  --allow-subdomains

# Set custom wrapper version
python3 tools/build_macos.py --wrapper-version "2.1.0"

# Use a custom .icns application icon
python3 tools/build_macos.py --icon "assets/digi_express.icns"

# Skip stripping quarantine from the project and toolchain
python3 tools/build_macos.py --skip-quarantine-strip

# Override the bundle identifier (default: com.digiexpress.admin)
# in .env: APP_BUNDLE_ID=com.example.myapp
```

> **Note**: Nuitka cannot produce Universal2 binaries. Use `--builder pyinstaller` (default) for a `universal` build, or `--builder nuitka` for a native `arm64`/`x86_64` build named after the host architecture.

#### Step 3.8 — Verify the build outputs
- `dist/DIGI Express Admin.app` — the application bundle (open with `open "dist/DIGI Express Admin.app"`)
- `macos/output/DIGI-Express-Admin-macOS-universal.app.zip` + `.sha256`
- `macos/output/DIGI-Express-Admin-macOS-universal.dmg` + `.sha256` (unless `--skip-dmg`)

---

## Build Engines: PyInstaller vs Nuitka

| | PyInstaller | Nuitka |
|---|---|---|
| **How it works** | Bundles `.pyc` bytecode + Python interpreter into a single archive | Translates every `.py` file to C, then compiles to native machine code |
| **Build time** | ~30–90 seconds | ~5–15 minutes (caches speed up subsequent builds) |
| **Output** | Python bytecode (can be decompiled) | Native `.exe` (extremely hard to reverse-engineer) |
| **Binary size** | Smaller | Larger |
| **Use case** | Development, internal tools | Production distribution, customer-facing apps |

**Nuitka build tips:**
- First builds are slow due to full C compilation. Subsequent builds reuse cached `.c` files.
- Use `--onedir` during development to skip the single-file compression step.
- Use `--debug` to keep the console window open for troubleshooting startup issues.

---

## X-Wrapper-Version Header

The desktop wrapper automatically injects an `X-Wrapper-Version` HTTP request header on **every** network request made by the embedded browser. This allows the backend to identify, validate, and enforce minimum wrapper versions.

### How It Works

| Layer | Mechanism |
|---|---|
| **Native requests** (Windows) | `CoreWebView2.WebResourceRequested` event attaches the header to all HTTP requests at the network layer |
| **JavaScript `fetch()` / `XMLHttpRequest`** | Injected user scripts monkey-patch `window.fetch` and `XMLHttpRequest.prototype.open` to add the header |
| **macOS WKWebView** | `WKUserScript` injected at document start patches `fetch` and `XMLHttpRequest` |

### Backend Usage Example

Your backend can read the header to enforce minimum version requirements:

```python
# Flask / Django example
wrapper_version = request.headers.get("X-Wrapper-Version")
if wrapper_version and wrapper_version < "2.0.0":
    return jsonify({"error": "Please update your desktop application"}), 426
```

### Configuration

Set the version in `.env` or at build time:
```env
APP_WRAPPER_VERSION=2.1.0
```
```powershell
python tools/build.py --wrapper-version "2.1.0"
```

---

## JavaScript Scripts Architecture

All browser-injected JavaScript is maintained as standalone `.js` files in `app/scripts/` for full IDE support (linting, syntax highlighting, error detection, type checking).

| File | Purpose |
|---|---|
| `swipe_navigation.js` | Mouse wheel horizontal swipe detection for back/forward browser navigation |
| `wrapper_version_header.js` | Intercepts `fetch()` and `XMLHttpRequest` to inject `X-Wrapper-Version` header |
| `prevent_file_drop.js` | Prevents accidental file drops from navigating the browser window away |

Scripts are loaded at runtime by `app/scripts_loader.py`, which:
- Resolves the correct scripts directory across development, PyInstaller (`sys._MEIPASS`), and Nuitka standalone builds.
- Caches file reads in memory with `@lru_cache`.
- Supports `{{PLACEHOLDER}}` template substitution for dynamic values (e.g., `{{WRAPPER_VERSION}}`).

---

## Testing & Static Analysis

Run the automated test suite and type analysis:

```powershell
# Run unit tests
python -m unittest discover -s tests

# Run static type and lint analysis (via Pyright)
npx pyright
```

---

## Keyboard Shortcuts

| Shortcut                       | Action                                                     |
| :----------------------------- | :--------------------------------------------------------- |
| `Ctrl+R` / `F5` / `Cmd+R`      | Normal reload; keeps cookies and site storage              |
| `Ctrl+Shift+R` / `Cmd+Shift+R` | Hard reload; clears HTTP cache and preserves login session |
| `Ctrl+Shift+Delete`            | Clear all browsing data, cache, and session (signs out)    |
| `Ctrl` + `+` / `-` / `0`       | Zoom in / out / reset                                      |
| `Ctrl` + Scroll Wheel          | Smooth zoom in / out                                       |
| `Alt+Left` / `Alt+Right`       | Navigate back / forward                                    |
| `Ctrl+Home`                    | Return to initial start URL                                |
| `F11`                          | Toggle fullscreen                                          |
| `Ctrl+W` / `Cmd+Q`             | Close application                                          |
| `Ctrl+F` / `Cmd+F`             | Find in page                                               |
| `Ctrl+P` / `Cmd+P`             | Print page                                                 |

---

## Gatekeeper & Quarantine Guide (macOS)

- The build script automatically strips `com.apple.quarantine` and Finder metadata (`xattr -cr`) on the local build machine.
- Before each build it also strips quarantine from the project tree and the local toolchain (Python interpreter, `lipo`, `iconutil`, `hdiutil`, `ditto`, `codesign`, `sips`), so a repo or dependency downloaded from the internet never trips Gatekeeper mid-build. Use `--skip-quarantine-strip` to disable this.
- For ad-hoc / internally distributed builds downloaded over the internet, Gatekeeper may flag the file. If prompted on a target Mac, run:
  ```bash
  xattr -cr /Applications/"DIGI Express Admin.app"
  ```
- For public distribution, sign with an Apple Developer ID certificate and notarize with `xcrun notarytool`.

---

## Performance & Security

- **Web Performance**: The wrapper runs the native browser engine directly. Optimize web assets (SPA routing, image compression, minimal layout shift) for optimal performance.
- **Security Boundary**: The embedded configuration (URL, app name) is plain configuration metadata within the binary. Use HTTPS in production and manage API authentication through the web application backend.
- **Nuitka Compilation**: When built with Nuitka, all Python source code is translated to C and compiled to native machine code, making reverse engineering significantly harder than bytecode-based packaging.
- **Error Handling**: Fatal startup errors are caught by a global exception handler and displayed in a native OS message box (Windows `MessageBoxW` / macOS `NSAlert`), preventing silent failures in windowed builds.
