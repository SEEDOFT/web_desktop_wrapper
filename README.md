# Native Desktop Wrapper (Windows & macOS)

A native desktop wrapper for modern web applications powered by **Microsoft Edge WebView2** on Windows and **Apple Cocoa WKWebView** on macOS.

---

## Table of Contents

- [Features](#features)
- [System Requirements](#system-requirements)
- [Quick Start](#quick-start)
- [Configuration (.env)](#configuration-env)
- [Build Commands \& Guide](#build-commands--guide)
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
| `EMBEDDED_WEBVIEW`            | `true`               | Use native embedded webview window (`true`) or open in default system browser (`false`)|
| `BUILDER_ENGINE`              | `pyinstaller`        | Compilation engine: `pyinstaller` (default) or `nuitka` (native C++ compilation)      |

---

## Build Commands & Guide

### 1. Build Windows Standalone Executable (.exe)

Compiles a standalone, single-file `.exe` embedding configuration and assets.

```powershell
# PyInstaller (default — fast build, bytecode packaging)
python tools/build.py

# Nuitka (native C++ compilation — slower build, maximum reverse-engineering defense)
python tools/build.py --builder nuitka

# Debug build (keeps console window visible for troubleshooting)
python tools/build.py --builder nuitka --debug
```

#### Custom Build Options:
```powershell
# Specify a custom starting URL and allow specific auth hosts
python tools/build.py `
  --url "https://app.company.com" `
  --allowed-host "login.company.com" `
  --allow-subdomains

# Set custom wrapper version
python tools/build.py --wrapper-version "2.1.0"

# Build a directory package instead of single executable
python tools/build.py --onedir
```

#### Build Outputs:
- `dist/DIGI Express Admin.exe`
- `dist/DIGI Express Admin.exe.sha256`

---

### 2. Build Windows Offline Installer (Setup.exe)

Builds a dual-architecture (x86 + x64) offline installer using **Inno Setup 6**. It bundles offline Evergreen WebView2 runtimes and automatically installs the appropriate architecture.

#### Prerequisites:
1. Install [Inno Setup 6](https://jrsoftware.org/isdl.php).
2. Download Microsoft Evergreen Standalone Installers into `installer/downloads/`:
   - `installer/downloads/MicrosoftEdgeWebView2RuntimeInstallerX86.exe`
   - `installer/downloads/MicrosoftEdgeWebView2RuntimeInstallerX64.exe`

#### Build Command:
```powershell
python tools/build_installer.py
```

#### Custom Toolchain Options:
```powershell
python tools/build_installer.py `
  --x64-python "C:\Python311\python.exe" `
  --x86-python "C:\Python311-32\python.exe" `
  --iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

#### Build Output:
- `installer/output/DIGI-Express-Admin-Setup.exe`
- `installer/output/DIGI-Express-Admin-Setup.exe.sha256`

---

### 3. Build macOS Universal App & DMG (.app / .dmg / .zip)

Builds a universal macOS application (`arm64` + `x86_64`), signs with hardened runtime, automatically strips quarantine/extended attributes, and creates distribution packages.

> **Note**: Must be run on macOS.

```bash
# Build Universal .app, .zip, and .dmg
python3 tools/build_macos.py

# Build .app and .zip only (skip DMG creation)
python3 tools/build_macos.py --skip-dmg
```

#### Build Outputs:
- `dist/DIGI Express Admin.app` (Application Bundle)
- `macos/output/DIGI-Express-Admin-macOS-universal.app.zip` (Zipped Bundle)
- `macos/output/DIGI-Express-Admin-macOS-universal.app.zip.sha256`
- `macos/output/DIGI-Express-Admin-macOS-universal.dmg` (Drag-and-Drop Disk Image)
- `macos/output/DIGI-Express-Admin-macOS-universal.dmg.sha256`

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
