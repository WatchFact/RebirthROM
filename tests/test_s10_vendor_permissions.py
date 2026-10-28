"""Regression tests for safe Exynos9820 vendor feature insertion."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ensure_s10_vendor_permissions.py"
FEATURES = ("android.hardware.security.model.compatible", "android.software.controls")


class VendorPermissionsTests(unittest.TestCase):
    def run_patch(self, contents):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handheld_core_hardware.xml"
            path.write_text(contents, encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
            return result, path.read_text(encoding="utf-8")

    def test_preserves_comments_and_other_features(self):
        source = '<?xml version="1.0" encoding="utf-8"?>\n<permissions>\n  <!-- original -->\n  <feature name="android.hardware.camera"/>\n</permissions>\n'
        result, text = self.run_patch(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('<!-- original -->', text)
        self.assertIn('android.hardware.camera', text)
        root = ET.fromstring(text)
        names = [e.get('name') for e in root.findall('feature')]
        for feature in FEATURES:
            self.assertEqual(names.count(feature), 1)

    def test_idempotent(self):
        source = '<permissions>\n  <feature name="android.software.controls"/>\n</permissions>\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'permissions.xml'
            path.write_text(source)
            for _ in range(2):
                result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            text = path.read_text()
            self.assertEqual(text.count('android.software.controls'), 1)
            self.assertEqual(text.count('android.hardware.security.model.compatible'), 1)

    def test_malformed_xml_is_not_modified(self):
        source = '<permissions><feature name="broken"></permissions>\n'
        result, text = self.run_patch(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(text, source)

    def test_wrong_root_is_not_modified(self):
        source = '<manifest/>\n'
        result, text = self.run_patch(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(text, source)

    def test_preserves_trailing_comment(self):
        source = '<permissions>\n</permissions>\n<!-- trailing -->\n'
        result, text = self.run_patch(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(text.endswith('<!-- trailing -->\n'))
        ET.fromstring(text)


if __name__ == '__main__':
    unittest.main()
