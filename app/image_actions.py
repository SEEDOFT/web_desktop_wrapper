from __future__ import annotations

import base64
import io
import ipaddress
import re
import socket
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import http.client
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

from PIL import Image
from app.navigation import is_navigation_allowed

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000


def origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    return parsed.scheme.lower(), (parsed.hostname or '').lower(), parsed.port or (443 if parsed.scheme == 'https' else 80)


def validate_target(url: str, page_url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Only HTTP image URLs are supported.')
    if origin(url) != origin(page_url) and parsed.scheme != 'https':
        raise ValueError('External images must use HTTPS.')


def public_connection(address: tuple[str, int], timeout: Any = socket._GLOBAL_DEFAULT_TIMEOUT, source_address: Any = None):
    """Connect to the validated address itself, preventing DNS rebinding."""
    addresses = socket.getaddrinfo(address[0], address[1], type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('External image servers must use public network addresses.')
    error = None
    for item in addresses:
        try:
            return socket.create_connection((item[4][0], address[1]), timeout, source_address)
        except OSError as exc:
            error = exc
    raise OSError('Image connection failed.') from error


class ImageRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, page_url: str):
        self.page_url = page_url

    def redirect_request(self, request, response, code, message, headers, new_url):
        validate_target(new_url, self.page_url)
        redirected = super().redirect_request(request, response, code, message, headers, new_url)
        if redirected is not None and origin(new_url) != origin(self.page_url):
            for key in ('Cookie', 'Authorization', 'X-wrapper-version'):
                redirected.remove_header(key)
        return redirected


class ImageHTTP(urllib.request.HTTPHandler):
    def __init__(self, page_url: str):
        super().__init__()
        self.page_url = page_url

    def http_open(self, request):
        def connection(host, **kwargs):
            result = http.client.HTTPConnection(host, **kwargs)
            if origin(request.full_url) != origin(self.page_url):
                result._create_connection = public_connection
            return result
        return self.do_open(connection, request)


class ImageHTTPS(urllib.request.HTTPSHandler):
    def __init__(self, page_url: str):
        super().__init__()
        self.page_url = page_url

    def https_open(self, request):
        def connection(host, **kwargs):
            result = http.client.HTTPSConnection(host, **kwargs)
            if origin(request.full_url) != origin(self.page_url):
                result._create_connection = public_connection
            return result
        return self.do_open(connection, request, context=self._context)


def checked_image(data: bytes, source: str) -> tuple[bytes, str]:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('Images must be no larger than 20 MB.')
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError('This image is too large to process safely.')
        extension = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp', 'GIF': 'gif', 'BMP': 'bmp', 'TIFF': 'tiff', 'ICO': 'ico'}.get(image.format)
        if not extension:
            raise ValueError('This image format is not supported by native image actions.')
        image.verify()
    name = Path(unquote(urlsplit(source).path)).stem
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)[:80].strip('_') or 'image'
    return data, name + '.' + extension


class ImageActions:
    def __init__(self, window: Any, config: Any):
        self.window = window
        self.config = config
        self._lock = threading.Lock()
        self._temporary = tempfile.TemporaryDirectory(prefix='wrapper-images-')
        self._share_type = None
        self._share_picker = None
        self._share_index = 0

    def close(self, *_args):
        self._temporary.cleanup()

    def _page(self) -> str:
        page = self.window.get_current_url() or ''
        if urlsplit(page).scheme not in ('http', 'https') or not is_navigation_allowed(page, self.config):
            raise ValueError('Image actions are available only on approved application pages.')
        return page

    def _retrieve(self, source: str, encoded: str | None, page: str) -> tuple[bytes, str]:
        source = urljoin(page, source)
        displayed = self.window.evaluate_js('Array.from(document.images, image => image.currentSrc || image.src)') or []
        if source not in displayed:
            raise ValueError('Open this image in the preview before using image actions.')
        if encoded is not None:
            if urlsplit(source).scheme not in ('blob', 'data'):
                raise ValueError('Local image data requires a local preview URL.')
            if len(encoded) > (MAX_IMAGE_BYTES * 4 // 3 + 4):
                raise ValueError('Images must be no larger than 20 MB.')
            return checked_image(base64.b64decode(encoded, validate=True), source)
        validate_target(source, page)
        headers = {'Accept': 'image/*'}
        if origin(source) == origin(page):
            cookies = []
            path = urlsplit(source).path
            for jar in self.window.get_cookies():
                for morsel in jar.values():
                    cookie_path = morsel['path'] or '/'
                    if path == cookie_path or path.startswith(cookie_path.rstrip('/') + '/'):
                        if not morsel['secure'] or urlsplit(source).scheme == 'https':
                            cookies.append(morsel.OutputString(attrs=[]))
            if cookies:
                headers['Cookie'] = '; '.join(cookies)
            if self.config.wrapper_version:
                headers['X-Wrapper-Version'] = self.config.wrapper_version
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), ImageRedirect(page), ImageHTTP(page), ImageHTTPS(page))
        with opener.open(urllib.request.Request(source, headers=headers), timeout=20) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
        return checked_image(data, source)

    def _ui(self, callback):
        completed = threading.Event()
        result = []
        errors = []
        def run():
            try:
                result.append(callback())
            except Exception as exc:
                errors.append(exc)
            finally:
                completed.set()
        if sys.platform == 'win32':
            from System import Action
            self.window.native.BeginInvoke(Action(run))
        elif sys.platform == 'darwin':
            from PyObjCTools import AppHelper
            AppHelper.callAfter(run)
        else:
            raise RuntimeError('Native image actions require Windows or macOS.')
        if not completed.wait(30):
            raise RuntimeError('The application did not respond to the image action.')
        if errors:
            raise errors[0]
        return result[0] if result else None

    def _copy(self, data: bytes):
        with Image.open(io.BytesIO(data)) as image:
            output = io.BytesIO()
            image.convert('RGBA').save(output, format='PNG')
            png = output.getvalue()
        if sys.platform == 'win32':
            import clr
            clr.AddReference('System.Drawing')
            clr.AddReference('System.Windows.Forms')
            from System import Array, Byte
            from System.Drawing import Bitmap
            from System.IO import MemoryStream
            from System.Windows.Forms import Clipboard
            def copy():
                stream = MemoryStream(Array[Byte](png))
                bitmap = Bitmap(stream)
                try:
                    Clipboard.SetImage(bitmap)
                finally:
                    bitmap.Dispose()
                    stream.Dispose()
            self._ui(copy)
        else:
            import AppKit
            import Foundation
            def copy():
                pasteboard = AppKit.NSPasteboard.generalPasteboard()
                pasteboard.clearContents()
                if not pasteboard.setData_forType_(Foundation.NSData.dataWithBytes_length_(png, len(png)), 'public.png'):
                    raise RuntimeError('The image could not be copied.')
            self._ui(copy)

    def _share(self, data: bytes, name: str):
        self._share_index += 1
        directory = Path(self._temporary.name) / str(self._share_index)
        directory.mkdir()
        path = directory / name
        path.write_bytes(data)
        if sys.platform == 'win32':
            import clr
            from System import Array, Object
            if self._share_type is None:
                root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
                library = root / 'media/WrapperImageShare.dll'
                if not library.is_file():
                    if getattr(sys, 'frozen', False):
                        raise RuntimeError('Rebuild this app with the native image sharing adapter.')
                    from app.windows_media import build_share_adapter
                    library = build_share_adapter(Path(self._temporary.name) / 'WrapperImageShare.dll')
                self._share_type = clr.AddReference(str(library)).GetType('WrapperImageShare')
            task = self._ui(lambda: self._share_type.GetMethod('Open').Invoke(None, Array[Object]([self.window.native.Handle, str(path)])))
            task.GetAwaiter().GetResult()
        else:
            import AppKit
            import Foundation
            def share():
                self._share_picker = AppKit.NSSharingServicePicker.alloc().initWithItems_([Foundation.NSURL.fileURLWithPath_(str(path))])
                view = self.window.native.contentView()
                self._share_picker.showRelativeToRect_ofView_preferredEdge_(AppKit.NSZeroRect, view, AppKit.NSMinYEdge)
            self._ui(share)

    def image_action(self, action: str, source: str, encoded: str | None = None) -> dict[str, str]:
        if not self._lock.acquire(blocking=False):
            return {'status': 'error', 'message': 'Another image action is still running.'}
        try:
            if action not in ('copy', 'save', 'share'):
                raise ValueError('Unknown image action.')
            page = self._page()
            if action == 'save' and not self.config.allow_downloads:
                raise ValueError('Downloads are disabled in this application.')
            data, name = self._retrieve(source, encoded, page)
            if origin(self._page()) != origin(page):
                raise ValueError('The application page changed. Open the image again.')
            if action == 'copy':
                self._copy(data)
                return {'status': 'success', 'message': 'Image copied.'}
            if action == 'save':
                import webview
                selected = self.window.create_file_dialog(webview.FileDialog.SAVE, save_filename=name)
                if not selected:
                    return {'status': 'cancelled', 'message': ''}
                destination = selected if isinstance(selected, str) else selected[0]
                Path(destination).write_bytes(data)
                return {'status': 'success', 'message': 'Image saved.'}
            self._share(data, name)
            return {'status': 'success', 'message': 'Share dialog opened.'}
        except urllib.error.HTTPError as exc:
            return {'status': 'error', 'message': f'The image server returned HTTP {exc.code}. Open the preview again to refresh its access link.'}
        except ValueError as exc:
            return {'status': 'error', 'message': str(exc)}
        except Exception:
            return {'status': 'error', 'message': 'The native image action failed. Check the connection and make sure this app was rebuilt with image-action support.'}
        finally:
            self._lock.release()
