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
- **Signed Mac Releases**: Direct releases use Developer ID signing, hardened runtime, Apple notarization, and stapled tickets.
- **X-Wrapper-Version Header**: Adds version metadata to approved Windows requests and same-origin JavaScript requests.
- **Dual Build Engines**: Supports both **PyInstaller** (fast packaging) and **Nuitka** (native C++ compilation for maximum reverse-engineering defense).
- **External JavaScript Scripts**: All injected browser scripts are standalone `.js` files in `app/scripts/` with full IDE linting, syntax highlighting, and error detection support.

---

## System Requirements

- **Windows**: Windows 10 / 11 (x64 or x86) with [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/).
- **macOS**: macOS 12 Monterey or later (Apple Silicon & Intel).
- **Python**: Python 3.10+ (Universal2 build required on macOS).

---

## Quick Start

### 1-Step Automated Build (Recommended)

#### macOS (Terminal):
```bash
# Automatically sets up .venv, installs dependencies, and builds with Nuitka
./build.sh
```

#### Windows (PowerShell):
```powershell
# Automatically sets up .venv, installs dependencies, and builds with Nuitka
.\build.ps1

# Or build the complete offline Windows Setup installer:
.\build.ps1 -Installer
```

---

### Manual Environment Setup

#### Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

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

### Development Mode

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
| `SHOW_SPLASH`                 | `true`               | Show branding while the web application loads                                        |
| `SPLASH_DURATION`             | `4.5`                | Legacy compatibility value; readiness now controls splash dismissal                   |
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
| `APP_WRAPPER_VERSION`         | `1.0.0`              | Embedded wrapper version; sent via headers for supported requests and macOS user-agent metadata |
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

To send a clean source snapshot to someone else (no `.venv`, build artifacts, downloads, or your `.env`), run the cleanup script:

```bash
# macOS / Linux
./tools/cleanup.sh

# Clean only, without creating the ZIP
./tools/cleanup.sh --skip-zip

# Clean and write the ZIP to a specific directory
./tools/cleanup.sh --output-dir ~/Desktop
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File tools/cleanup.ps1

# Clean only, without creating the ZIP
powershell -ExecutionPolicy Bypass -File tools/cleanup.ps1 -SkipZip

# Clean and write the ZIP to a specific directory
powershell -ExecutionPolicy Bypass -File tools/cleanup.ps1 -OutputDir D:\shares
```

The script removes `.venv`, `.build-tools`, `build/`, `dist/`, installer and macOS outputs, offline WebView2 downloads, `__pycache__`, `.icns`, `.spec`, `.DS_Store`, and your `.env` (the recipient must copy `.env.example` → `.env`). The zip excludes the `.git` folder. Source-only project size is ~0.5 MB.

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

Builds a Universal2 macOS application (`arm64` + `x86_64`) with PyInstaller or a host-architecture app with Nuitka, then creates ZIP and DMG packages. Development builds are ad-hoc signed; direct releases use Developer ID and notarization.

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

#### Step 3.6 — Build a development .app, ZIP, and DMG
```bash
# PyInstaller (default — universal2 build, ~30–90 s)
python3 tools/build_macos.py

# Build .app and .zip only (skip DMG creation)
python3 tools/build_macos.py --skip-dmg
```
The script:
1. Loads `.env` before resolving build defaults, validates its settings, and embeds the complete environment in an isolated temporary source copy.
2. Generates a multi-resolution `.icns` from `assets/digi_portrait.jpg` (or landscape fallback).
3. Compiles the `.app`, validates every bundled architecture, and patches `Info.plist`.
4. Ad-hoc signs development builds, or performs Developer ID signing and notarization for direct releases.
5. Creates the ZIP and DMG, then writes checksums after all signing and stapling changes.

The `.env` file is not shipped as a sidecar file. Its complete text and validated
runtime configuration are embedded in an isolated temporary source copy, so the
built app works without an external `.env`. Builds never overwrite the repository's
`app/embedded_config.py`; temporary sources are cleaned on success or failure.

For repeatable macOS dependencies, install `requirements-macos.lock.txt` (the
tested CPython 3.14 environment). The Nuitka pipeline uses this exact lock file
and does not automatically upgrade pip. Update the lock deliberately after
running both the Python suite and the native regression fixture.

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

# Override the bundle identifier (default: com.digiexpress.admin)
# in .env: APP_BUNDLE_ID=com.example.myapp
```

> **Note**: Nuitka cannot produce Universal2 binaries. Use `--builder pyinstaller` (default) for a `universal` build, or `--builder nuitka` for a native `arm64`/`x86_64` build named after the host architecture.

#### Step 3.8 — Verify the build outputs
- `dist/DIGI Express Admin.app` — the application bundle (open with `open "dist/DIGI Express Admin.app"`)
- `macos/output/DIGI-Express-Admin-macOS-universal.app.zip` + `.sha256`
- `macos/output/DIGI-Express-Admin-macOS-universal.dmg` + `.sha256` (unless `--skip-dmg`)

#### Step 3.9 — Create a DMG for other Macs

A public download needs an Apple Developer Program membership and a
**Developer ID Application** certificate. After enrollment, install the certificate
and its private key in your login keychain. Confirm the exact identity:

```bash
security find-identity -v -p codesigning
```

Create a Keychain profile for Apple's notarization service. Use an app-specific
password for the Apple ID account:

```bash
xcrun notarytool store-credentials "digi-notary" \
  --apple-id "developer@example.com" \
  --team-id "YOUR_TEAM_ID" \
  --password "YOUR_APP_SPECIFIC_PASSWORD"
```

Build, sign, notarize, staple, and verify a Universal2 release:

```bash
python3 tools/build_macos.py \
  --distribution direct \
  --builder pyinstaller \
  --signing-identity "Developer ID Application: Your Company (YOUR_TEAM_ID)" \
  --notary-profile "digi-notary"
```

For a smaller native-architecture release, replace `pyinstaller` with `nuitka`.
Nuitka output is labeled `arm64` or `x86_64`; create and share both DMGs if you
need to support both Mac architectures.

The command stops if signing, architecture validation, notarization, stapling,
or Gatekeeper assessment fails. Submission responses are saved as
`macos/output/notarization-*.json`. Share the final `.dmg` and its `.sha256`
file. Recipients open the DMG and drag the app to Applications; no Terminal
command or Gatekeeper bypass should be required. macOS can show its normal
first-launch confirmation.

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

The desktop wrapper adds `X-Wrapper-Version` to approved native navigation and
same-origin JavaScript requests. This metadata identifies the wrapper version;
it is not proof of authentication.

### How It Works

| Layer | Mechanism |
|---|---|
| **Native requests** (Windows) | `CoreWebView2.WebResourceRequested` event attaches the header to all HTTP requests at the network layer |
| **JavaScript `fetch()` / `XMLHttpRequest`** | Injected user scripts monkey-patch `window.fetch` and `XMLHttpRequest.prototype.open` to add the header |
| **macOS WKWebView** | Approved native navigations are copied and receive only the version header change; a document-start script covers `fetch` and XHR |

On macOS, normal link navigation and native HTML form submission are left to
WKWebView so website click and submit handlers retain their standard behavior.
The wrapper adds `X-Wrapper-Version` to every approved native HTTP(S) navigation,
including the initial page, links, retries, redirects, and form POSTs. On macOS,
it uses the request's native mutable copy and changes only the version header;
the original POST body, cookies, method, and request properties stay intact.
JavaScript `fetch()` and XHR calls also receive the explicit header.

On macOS, native header replay is restricted to the main frame and compares
header names case-insensitively. Child frames and popup targets are handed to
WebKit's native routing, so their requests cannot replace the main document.
Child frames and parser-loaded resources retain `DigiWrapper/<version>` in their
user-agent as version metadata; WKWebView has no public per-frame request-header
injection hook. Popup links handled in the current window subsequently pass
through the main-frame header policy.

The wrapper displays a top loading indicator on Livewire navigation events and
normal link/form navigation. It lives outside the page body, survives Livewire
page swaps, and ignores pointer input so it cannot block website controls.
Native failures and blocked navigations clear the indicator immediately.
If the site cannot be reached, the local recovery page offers **Refresh** and
**Close**. Refresh retries an approved GET destination with the wrapper version
header; it does not resubmit a failed form POST. Recovery controls are available
only on the local error document, and technical URLs are not displayed.

### Backend Usage Example

Compare parsed version numbers
(string comparisons incorrectly order versions such as `1.0.10` and `1.0.2`):

```python
# Flask example; packaging must be installed on the server
import re
from packaging.version import InvalidVersion, Version

match = re.search(r"(?:^|\s)DigiWrapper/([0-9.]+)(?:\s|$)", request.headers.get("User-Agent", ""))
wrapper_version = request.headers.get("X-Wrapper-Version") or (match.group(1) if match else None)
try:
    outdated = wrapper_version is not None and Version(wrapper_version) < Version("1.0.1")
except InvalidVersion:
    outdated = True
if outdated:
    return jsonify({"error": "Please update your desktop application"}), 426
```

### Configuration

Set the version in `.env` or at build time:

Every build embeds the full `.env` text inside the generated configuration module
and loads it from memory at startup, without an external `.env` file. Explicit
build arguments override corresponding application settings. Rebuild and install
the new app after changing settings. All values in `.env` become part of the
distributed application; embedded values remain recoverable by someone who can
inspect the running application.
Nuitka builds use the standard compiler without paid plugins or a Commercial
license. The embedded `.env` is compiled with the application code; native
compilation makes source inspection harder but does not encrypt configuration
values.
The build log prints the embedded version. For the macOS Nuitka pipeline:

```bash
bash tools/build_nuitka_all.sh --wrapper-version 1.0.1
```

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

# Lint Python (install Ruff separately if needed)
ruff check .

# JavaScript request/header and navigation lifecycle regressions
node --test tests/navigation_progress.test.cjs tests/wrapper_headers.test.cjs
```

On macOS, run the real WKWebView regression fixture:

```bash
python3 -m tests.wkwebview_smoke
# Verify the startup timeout screen against a stalled server
python3 -m tests.wkwebview_smoke --startup-hang
```

This opens and closes a temporary browser window using a localhost server and
synthetic data. It checks modal/detail buttons, dropdowns, loading completion and
cancellation, POST bodies with CSRF/cookies, request headers, iframe and popup
routing, redirects, and back/forward history. Its Livewire lifecycle checks use
synthetic events; production Livewire behavior and physical pointer delivery
still require manual checks. It does not access the DIGI server or build artifacts.

Packaged applications write sanitized, rotating diagnostics to `Logs/wrapper.log`
beside their WebKit/WebView2 profile directory (four files of up to 1 MiB each).
Logs record startup version and configuration source; URL details and common
credential fields are redacted. Console verbosity remains controlled by
`LOG_LEVEL`, and both PyInstaller and Nuitka are recognized as packaged runtimes.

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

- Development builds use an ad-hoc signature and can be blocked when downloaded on another Mac.
- Direct builds use hardened runtime, a secure timestamp, Developer ID signing, Apple notarization, and stapled tickets.
- The build does not remove quarantine from the source tree, Python installation, toolchain, or release artifacts.
- Test the uploaded DMG after downloading it through a browser so Gatekeeper evaluates the same file your users receive.

---

## Performance & Security

- **Web Performance**: The wrapper runs the native browser engine directly. Optimize web assets (SPA routing, image compression, minimal layout shift) for optimal performance.
- **Security Boundary**: The embedded configuration (URL, app name) is plain configuration metadata within the binary. Use HTTPS in production and manage API authentication through the web application backend.
- **Nuitka Compilation**: When built with Nuitka, all Python source code is translated to C and compiled to native machine code, making reverse engineering significantly harder than bytecode-based packaging.
- **Error Handling**: Fatal startup errors are caught by a global exception handler and displayed in a native OS message box (Windows `MessageBoxW` / macOS `NSAlert`), preventing silent failures in windowed builds.
