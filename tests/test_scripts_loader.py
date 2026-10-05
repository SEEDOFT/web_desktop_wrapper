from __future__ import annotations

import unittest

from app.scripts_loader import get_script


class ScriptsLoaderTests(unittest.TestCase):
    def test_load_swipe_navigation_script(self) -> None:
        script = get_script("swipe_navigation.js", THRESHOLD=150, COOLDOWN_MS=800)
        self.assertIn('parseInt("150", 10) || 100;', script)
        self.assertIn('parseInt("800", 10) || 600;', script)
        self.assertIn("window.__wdwSwipeNavigationInstalled", script)

    def test_load_wrapper_version_header_script(self) -> None:
        script = get_script("wrapper_version_header.js", WRAPPER_VERSION="2.1.0")
        self.assertIn('var wrapperVersion = "2.1.0";', script)
        self.assertIn("X-Wrapper-Version", script)
        self.assertIn("origFetch", script)
        self.assertIn("XMLHttpRequest.prototype.open", script)
        self.assertIn("window.__wdwWrapperVersionHeaderInstalled", script)
        self.assertNotIn('addEventListener("submit"', script)
        self.assertNotIn("preventDefault", script)
        self.assertNotIn("XMLHttpRequest.prototype.send", script)
        self.assertIn("window.location.origin", script)
        self.assertIn("Object.assign", script)
        self.assertIn("wdw-navigation-progress-style", script)
        self.assertIn("livewire:navigated", script)
        self.assertIn("z-index: 2147483647", script)

    def test_load_prevent_file_drop_script(self) -> None:
        script = get_script("prevent_file_drop.js")
        self.assertIn("dragover", script)
        self.assertIn("drop", script)
        self.assertIn("isDropzone", script)

    def test_nonexistent_script(self) -> None:
        script = get_script("non_existent_file.js")
        self.assertEqual(script, "")


if __name__ == "__main__":
    unittest.main()
