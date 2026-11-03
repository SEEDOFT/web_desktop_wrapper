import base64
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from app.image_actions import ImageActions, ImageRedirect, checked_image, public_connection, validate_target
from urllib.request import Request


def png():
    output = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(output, format='PNG')
    return output.getvalue()


class ImageActionTests(unittest.TestCase):
    def setUp(self):
        self.window = Mock()
        self.window.get_current_url.return_value = 'https://portal.example.test/page'
        self.window.evaluate_js.return_value = ['https://cdn.example.test/photo.png', 'blob:https://portal.example.test/preview']
        self.config = SimpleNamespace(allow_downloads=True, wrapper_version='1.0.0', allow_insecure_http=False,
                                      is_host_allowed=lambda host: host == 'portal.example.test')
        self.actions = ImageActions(self.window, self.config)
        self.addCleanup(self.actions.close)

    def test_local_image_copy_does_not_fetch(self):
        with patch.object(self.actions, '_copy') as copy, patch('urllib.request.build_opener') as fetch:
            result = self.actions.image_action('copy', 'blob:https://portal.example.test/preview', base64.b64encode(png()).decode())
        self.assertEqual(result['message'], 'Image copied.')
        copy.assert_called_once_with(png())
        fetch.assert_not_called()

    def test_external_image_is_read_without_application_cookies(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = png()
        opener = Mock()
        opener.open.return_value = response
        with patch('urllib.request.build_opener', return_value=opener):
            data, name = self.actions._retrieve('https://cdn.example.test/photo.png', None, self.window.get_current_url())
        self.assertEqual(name, 'photo.png')
        self.assertEqual(data, png())
        request = opener.open.call_args.args[0]
        self.assertFalse(request.has_header('Cookie'))
        self.assertFalse(request.has_header('X-wrapper-version'))
        self.window.get_cookies.assert_not_called()

    def test_save_writes_original_bytes_and_cancellation_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'image.png'
            self.window.create_file_dialog.return_value = [str(destination)]
            with patch.object(self.actions, '_retrieve', return_value=(png(), 'image.png')):
                result = self.actions.image_action('save', 'https://cdn.example.test/photo.png')
            self.assertEqual(result['message'], 'Image saved.')
            self.assertEqual(destination.read_bytes(), png())
            self.window.create_file_dialog.return_value = None
            with patch.object(self.actions, '_retrieve', return_value=(png(), 'image.png')):
                self.assertEqual(self.actions.image_action('save', 'https://cdn.example.test/photo.png')['status'], 'cancelled')

    def test_download_policy_is_checked_before_retrieval(self):
        self.config.allow_downloads = False
        with patch.object(self.actions, '_retrieve') as retrieve:
            self.assertEqual(self.actions.image_action('save', '/image.png')['status'], 'error')
        retrieve.assert_not_called()

    def test_untrusted_page_and_non_displayed_source_are_rejected(self):
        self.assertEqual(self.actions.image_action('copy', 'https://cdn.example.test/other.png')['status'], 'error')
        self.window.get_current_url.return_value = 'https://untrusted.example.test/'
        with patch.object(self.actions, '_retrieve') as retrieve:
            self.assertEqual(self.actions.image_action('copy', '/image.png')['status'], 'error')
        retrieve.assert_not_called()

    def test_redirect_drops_credentials_and_rejects_non_http_sources(self):
        request = Request('https://portal.example.test/a', headers={'Cookie': 'session=private', 'X-Wrapper-Version': '1.0.0'})
        redirected = ImageRedirect('https://portal.example.test/').redirect_request(request, None, 302, '', {}, 'https://cdn.example.test/a')
        self.assertFalse(redirected.has_header('Cookie'))
        self.assertFalse(redirected.has_header('X-wrapper-version'))
        for url in ('file:///etc/passwd', 'http://external.test/a', 'https://user:pass@external.test/a'):
            with self.assertRaises(ValueError):
                validate_target(url, 'https://portal.example.test/')

    def test_external_private_addresses_are_rejected_before_connecting(self):
        for address in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1'):
            with patch('socket.getaddrinfo', return_value=[(0, 0, 0, '', (address, 443))]), patch('socket.create_connection') as connect:
                with self.assertRaises(ValueError):
                    public_connection(('cdn.example.test', 443))
                connect.assert_not_called()

    def test_invalid_content_and_oversized_images_are_rejected(self):
        with self.assertRaises(Exception):
            checked_image(b'<html>Login</html>', '/a.png')
        with patch('app.image_actions.MAX_IMAGE_BYTES', 4), self.assertRaises(ValueError):
            checked_image(png(), '/a.png')

    def test_share_reports_opening_instead_of_claiming_delivery(self):
        with patch.object(self.actions, '_retrieve', return_value=(png(), 'image.png')), patch.object(self.actions, '_share') as share:
            result = self.actions.image_action('share', 'https://cdn.example.test/photo.png')
        share.assert_called_once_with(png(), 'image.png')
        self.assertEqual(result['message'], 'Share dialog opened.')


if __name__ == '__main__':
    unittest.main()
