# Native Edge WebView2 Desktop Wrapper

This Windows desktop wrapper now uses Microsoft Edge WebView2 through
`pywebview` instead of Qt WebEngine.

WebView2 uses the installed Microsoft Edge Chromium rendering engine. The
result should behave much closer to opening the same application in Edge,
without an address bar or browser tabs.

## Why this version is smoother

The previous version bundled Qt and Qt WebEngine, which introduced a separate
window-composition layer and separate Chromium build. This version:

- Uses the Windows-native Edge WebView2 control.
- Uses Edge's GPU rendering and media stack without overriding GPU flags.
- Opens the native window only after the first DOM-ready frame.
- Does not add or remove loading widgets around the web viewport.
- Uses per-monitor DPI awareness.
- Keeps cookies and WebView2 browser data in an application-specific folder.
- Disables DevTools, browser context menus, browser accelerator keys, status
  text, and remote debugging.
- Replaces WebView2's built-in error page with a branded page that never
  exposes the failed URL or web application host.
- Preserves the plain build-time configuration and one-file packaging.

Microsoft Edge WebView2 Runtime must be installed. It is included with Windows
11 and is present on most Windows 10 systems.

For deployment to Windows 10 computers where WebView2 might be absent, build
the offline installer described below. It contains both x86 and x64 WebView2
runtimes and installs the correct one automatically.

## Keyboard shortcuts

The wrapper re-enables a small set of shortcuts through the WebView2
`AcceleratorKeyPressed` event:

| Shortcut                        | Action                                                          |
| ------------------------------- | --------------------------------------------------------------- |
| `Ctrl+R`, `F5`                  | Normal reload; keeps cookies and site storage                   |
| `Ctrl+Shift+R`, `Ctrl+Shift+F5` | Hard reload; clears HTTP cache only and keeps the login session |
| `Ctrl+Shift+Delete`             | Clear all browsing data and reload (signs out)                  |
| `Ctrl` + `=` / `-` / `0`        | Zoom in / out / reset                                           |
| `Ctrl` + scroll wheel           | Zoom in / out                                                   |
| `Alt+Left` / `Alt+Right`        | Go back / forward                                               |
| `Ctrl+Home`                     | Navigate to the start URL                                       |
| `F11`                           | Toggle fullscreen                                               |
| `Ctrl+W`                        | Close the application                                           |
| `Ctrl+F`                        | Find on page                                                    |
| `Ctrl+P`                        | Print                                                           |

Zoom also works with the numeric keypad's `+`, `-`, and `0` keys. A two-finger
horizontal swipe on a precision touchpad navigates back or forward, and touch
devices can swipe from the left or right edge for the same behavior. The set of
keyboard shortcuts is defined in `_shortcut_action()` in `app/browser.py`; add
another case there to bind more keys.

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Do not install PySide6, PyQt, or CEF in this virtual environment. A clean
environment prevents PyInstaller from collecting unused browser engines.

## Development

Edit `.env`:

```dotenv
WEB_APP_URL=http://127.0.0.1:8000
APP_NAME=Your Desktop App
APP_ORGANIZATION=YourCompany

PERSIST_SESSION=true
PAGE_BACKGROUND_COLOR=#ffffff
```

Start the local web application, then the desktop wrapper:

```powershell
php artisan serve --host=127.0.0.1 --port=8000
python -m app
```

For a dark application, set the native pre-render background to the same color
used by the web application:

```dotenv
PAGE_BACKGROUND_COLOR=#111827
```

## Build one executable

For production, use an HTTPS address:

```dotenv
WEB_APP_URL=https://app.company.com
```

Build:

```powershell
python tools/build.py
```

Output:

```text
dist/Your Desktop App.exe
dist/Your Desktop App.exe.sha256
```

The application forces the `edgechromium` renderer. It does not silently fall
back to the legacy Internet Explorer control.

## Additional trusted hosts

Add only hosts required for authentication or application navigation:

```powershell
python tools/build.py `
  --allowed-host "login.company.com"
```

Subdomains remain blocked unless explicitly enabled:

```powershell
python tools/build.py --allow-subdomains
```

## Performance diagnosis

After this conversion, persistent lag that also occurs in Microsoft Edge is a
web-application issue rather than a Python window-host issue. Common causes are:

- full-document navigation instead of SPA navigation;
- large unoptimized images or video;
- repeated DOM replacement;
- expensive CSS blur, shadows, backdrop filters, or animations;
- synchronous JavaScript on the main thread;
- layout shifts caused by late fonts, images, and components;
- development-mode hot reload and source maps;
- Laravel debug mode or an unoptimized frontend development build.

Test the production frontend and API separately in Microsoft Edge. The wrapper
cannot make a slow page faster than Edge renders it.

## Security boundary

The build-time configuration (starting URL, name, options) is embedded in the
executable as plain values. It is not a secret: the executable must contain it
to run, and a desktop client cannot hide its network destination from the
operating system, DNS infrastructure, routers, proxies, or authorized network
inspection.

For protection of runtime secrets (API tokens, refresh tokens), Windows DPAPI
is the appropriate native mechanism if the application later needs it. This
wrapper intentionally does not ship a secret-storage layer; keep secrets out
of the executable and let the hosted web application handle its own
authentication.
## Build one offline x86/x64 installer

Build `DIGI Express Admin.exe` once with 32-bit Python and once with 64-bit
Python. Then download Microsoft's x86 and x64 Evergreen Standalone WebView2
installers into `installer/downloads` using these filenames:

- `MicrosoftEdgeWebView2RuntimeInstallerX86.exe`
- `MicrosoftEdgeWebView2RuntimeInstallerX64.exe`

With the workspace x86 toolchain and Inno Setup 6 installed, build both
architectures and the final installer with one command:

```powershell
python tools/build_installer.py
```

The script verifies the Python architectures and prerequisites, builds x64,
builds x86, restores the normal `dist` output to x64, compiles the installer,
and generates SHA-256 checksum files. Use `--x64-python`, `--x86-python`, or
`--iscc` only when those tools are installed in non-default locations.

The resulting `installer/output/DIGI-Express-Admin-Setup.exe` requires Windows
10 or later. It detects the operating-system architecture, installs WebView2
only when missing, and installs the matching application executable. The
installer is fully offline and requests administrator permission because the
WebView2 runtime is installed machine-wide. Its Start Menu and desktop
shortcuts are created automatically and named `DIGI Express Admin`.

## Build the universal macOS application

The macOS version uses the native Cocoa/WKWebView renderer and supports macOS
12 or later on both Apple silicon and Intel Macs. It must be built on macOS;
PyInstaller cannot create a Mac application from Windows.

Install a universal2 Python distribution and the Mac dependencies:

```bash
python3 -m pip install -r requirements-macos.txt
```

Build the universal application, ZIP archive, unsigned DMG, and checksums:

```bash
python3 tools/build_macos.py
```

Outputs:

```text
macos/output/DIGI-Express-Admin-macOS-universal.app.zip
macos/output/DIGI-Express-Admin-macOS-universal.app.zip.sha256
macos/output/DIGI-Express-Admin-macOS-universal.dmg
macos/output/DIGI-Express-Admin-macOS-universal.dmg.sha256
```

The script deletes previous Mac build artifacts, verifies that Python contains
both `arm64` and `x86_64` slices, builds the `.app`, verifies its executable
with `lipo`, and creates a DMG with an Applications-folder link. The bundle ID
is `com.digiexpress.admin`, which keeps WKWebView website data associated with
the same application between releases.

This first DMG is unsigned and unnotarized. It is suitable for internal testing,
but users must approve it manually in macOS Privacy & Security. Public releases
should use a Developer ID Application certificate, hardened runtime, Apple
notarization, and ticket stapling.
