"""Opt-in native regression: python -m tests.wkwebview_smoke (macOS GUI required)."""
from __future__ import annotations

import socket
import sys
import threading
import time
from dataclasses import replace
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs

import webview

from app.browser import _startup_watchdog, run_browser
from app.config import AppConfig

PAGE = """<!doctype html><title>Wrapper regression fixture</title>
<button id="detail" onclick="document.getElementById('dialog').showModal()">Detail</button>
<dialog id="dialog"><button onclick="this.closest('dialog').close()">Close</button></dialog>
<button id="dropdown" onclick="document.getElementById('menu').hidden=false">Dropdown</button>
<div id="menu" hidden>Menu</div>
<form id="login" method="post" action="/submit"><input name="csrf" value="fixture-csrf">
<input name="username" value="fixture"><button type="submit">Login</button></form>
<iframe name="child" id="child" src="/frame"></iframe>
<a id="frame-link" target="child" href="/frame-next">Child frame</a>
<a id="popup" target="_blank" href="/popup">Popup</a>
<a id="redirect" href="/redirect">Redirect</a>"""


def main() -> int:
    if sys.platform != "darwin":
        print("SKIP: WKWebView smoke test requires macOS")
        return 0
    requests: list[tuple[str, str, str | None]] = []
    failures: list[str] = []
    ready = threading.Event()
    closed = threading.Event()
    unreachable = threading.Event()
    startup_hang = "--startup-hang" in sys.argv
    release_startup = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def respond(self, status: int, content: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Set-Cookie", "fixture_session=valid; Path=/; SameSite=Lax")
            self.end_headers()
            try:
                self.wfile.write(content.encode())
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self) -> None:
            version = self.headers.get("X-Wrapper-Version")
            requests.append(("GET", self.path, version))
            if self.path == "/hang" and not release_startup.is_set():
                release_startup.wait(20)
            if self.path.startswith("/unreachable") and unreachable.is_set():
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            # Public WKWebView has no per-frame loadRequest API; frames keep their
            # native context and identify the version through the user-agent.
            frame = self.path in {"/frame", "/frame-next"}
            if version != "1.0.1" and not (frame and "DigiWrapper/1.0.1" in self.headers.get("User-Agent", "")):
                self.respond(426, "Version required")
            elif self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/done")
                self.end_headers()
            else:
                self.respond(200, PAGE if self.path == "/" else f"<title>{self.path}</title><p id='result'>ok</p>")

        def do_POST(self) -> None:
            version = self.headers.get("X-Wrapper-Version")
            requests.append(("POST", self.path, version))
            body = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode())
            if (version != "1.0.1" or body.get("csrf") != ["fixture-csrf"]
                or body.get("username") != ["fixture"] or "fixture_session=valid" not in self.headers.get("Cookie", "")):
                self.respond(419, "Session or version failure")
            else:
                self.respond(200, "<title>POST accepted</title><p id='result'>post accepted</p>")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    create_window = webview.create_window

    def create(*args, **kwargs):
        window = create_window(*args, **kwargs)
        assert window is not None
        window.events.loaded += ready.set
        window.events.closed += closed.set
        return window

    def driver() -> None:
        window = None
        try:
            if not ready.wait(20):
                raise AssertionError("Initial fixture failed to load")
            window = webview.windows[-1]

            def wait_for(script: str) -> None:
                assert window is not None
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if window.evaluate_js(script):
                        return
                    time.sleep(0.1)
                raise AssertionError(f"Timed out: {script}")

            if startup_hang:
                wait_for("!!document.getElementById('wdw-unreachable-page') && !!window.pywebview && !!window.pywebview.api")
                wait_for("document.getElementById('retry-btn').getBoundingClientRect().height > 0 && document.getElementById('close-btn').getBoundingClientRect().height > 0")
                release_startup.set()
                window.evaluate_js("document.getElementById('retry-btn').click()")
                wait_for("document.title==='/hang'")
                assert all(version == "1.0.1" for _, route, version in requests if route == "/hang"), requests
                print("PASS: stalled startup displays recovery screen; Refresh recovers with version header", flush=True)
                return

            wait_for("!!window.__wdwNavigationProgress")
            window.evaluate_js("document.getElementById('detail').click()")
            wait_for("document.getElementById('dialog').open")
            window.evaluate_js("document.getElementById('dialog').close();document.getElementById('dropdown').click()")
            wait_for("!document.getElementById('menu').hidden")
            window.evaluate_js("document.dispatchEvent(new CustomEvent('livewire:navigate'))")
            wait_for("document.getElementById('wdw-navigation-progress').style.display==='block'")
            window.evaluate_js("document.dispatchEvent(new CustomEvent('livewire:navigated'))")
            wait_for("document.getElementById('wdw-navigation-progress').style.display==='none'")
            window.evaluate_js(
                f"window.__wdwNavigationProgress.start();location.href='http://localhost:{server.server_port}/blocked'"
            )
            wait_for("document.getElementById('wdw-navigation-progress').style.display==='none'")
            assert not any(route == "/blocked" for _, route, _ in requests), requests
            window.evaluate_js("fetch('/api', {headers:{'x-wrapper-version':'old'}}).then(()=>document.documentElement.dataset.api='ok')")
            wait_for("document.documentElement.dataset.api==='ok'")
            window.evaluate_js("document.getElementById('frame-link').click()")
            wait_for("document.getElementById('child').contentWindow.location.pathname==='/frame-next'")
            wait_for("location.pathname==='/' && !!document.getElementById('detail')")
            window.evaluate_js("document.getElementById('login').requestSubmit()")
            wait_for("document.title==='POST accepted'")
            window.load_url(base)
            wait_for("!!document.getElementById('popup')")
            window.evaluate_js("document.getElementById('popup').click()")
            wait_for("location.pathname==='/popup'")
            window.load_url(base)
            wait_for("!!document.getElementById('redirect')")
            window.evaluate_js("document.getElementById('redirect').click()")
            wait_for("location.pathname==='/done'")
            window.evaluate_js("history.back()")
            wait_for("location.pathname==='/'")
            window.evaluate_js("history.forward()")
            wait_for("location.pathname==='/done'")
            assert all(version == "1.0.1" for _, route, version in requests if route not in {"/frame", "/frame-next", "/favicon.ico"}), requests
            assert sum(method == "POST" for method, _, _ in requests) == 1, requests
            unreachable.set()
            window.load_url(base + "/unreachable")
            wait_for("!!document.getElementById('wdw-unreachable-page') && !!window.pywebview && !!window.pywebview.api")
            unreachable.clear()
            window.evaluate_js("document.getElementById('retry-btn').click()")
            wait_for("document.title==='/unreachable'")
            assert any(route == "/unreachable" and version == "1.0.1" for _, route, version in requests), requests
            unreachable.set()
            window.load_url(base + "/unreachable-close")
            wait_for("!!document.getElementById('wdw-unreachable-page') && !!window.pywebview && !!window.pywebview.api")
            window.evaluate_js("document.getElementById('close-btn').click()")
            if not closed.wait(10):
                raise AssertionError("Close action did not close the error window")
            print("PASS: native interactions, POST+CSRF+cookies, frame routing, history, unreachable page refresh+close", flush=True)
        except Exception as exc:
            failures.append(str(exc))
            print(f"FAIL: {exc}", flush=True)
        finally:
            if window is None and webview.windows:
                window = webview.windows[-1]
            if window is not None and not closed.is_set():
                window.destroy()

    with patch.dict("os.environ", {"WEB_APP_URL": base}, clear=True):
        config = replace(AppConfig.load(packaged=False), app_name="WKWebView regression fixture",
            web_app_url=base + "/hang" if startup_hang else base, allowed_hosts=("127.0.0.1",), wrapper_version="1.0.1",
            show_splash=False, enable_tray=False, persist_session=False, single_instance=False,
            start_maximized=False, open_external_links=False, run_on_startup=False)
    threading.Thread(target=driver, daemon=True).start()
    try:
        with patch("webview.create_window", side_effect=create), patch(
            "app.browser._startup_watchdog", partial(_startup_watchdog, timeout_seconds=2 if startup_hang else 15)
        ):
            run_browser(config)
    finally:
        server.shutdown()
        server.server_close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
