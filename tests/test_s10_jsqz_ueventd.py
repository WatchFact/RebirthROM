"""Regression tests for the imported Android 16 vendor JSQZ ueventd rule."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ensure_s10_jsqz_ueventd import ensure_rule, RULE


class JsqzUeventdTests(unittest.TestCase):
    def test_appends_to_imported_file_once(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "vendor" / "etc" / "ueventd.rc"
            path.parent.mkdir(parents=True)
            path.write_text("# stock\n/dev/snd/* 0660 system audio\n")
            self.assertTrue(ensure_rule(path))
            once = path.read_bytes()
            self.assertFalse(ensure_rule(path))
            self.assertEqual(path.read_bytes(), once)
            self.assertEqual(path.read_text().count("/dev/jsqz"), 1)
            self.assertIn("# stock\n", path.read_text())

    def test_rejects_conflicting_rule_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ueventd.rc"
            content = "/dev/jsqz 0666 root root\n"
            path.write_text(content)
            with self.assertRaisesRegex(ValueError, "conflicting"):
                ensure_rule(path)
            self.assertEqual(path.read_text(), content)

    def test_rejects_missing_imported_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "vendor" / "etc" / "ueventd.rc"
            with self.assertRaisesRegex(ValueError, "missing"):
                ensure_rule(path)
            self.assertFalse(path.exists())

    def test_preserves_crlf_and_existing_comment(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ueventd.rc"
            path.write_bytes(b"# /dev/jsqz not active\r\n/dev/null 0666 root root\r\n")
            ensure_rule(path)
            self.assertEqual(path.read_bytes().count(b"/dev/jsqz"), 2)
            self.assertTrue(path.read_bytes().endswith(" ".join(RULE).encode() + b"\r\n"))

    def test_vendor_module_uses_android16_imported_path(self):
        source = (Path(__file__).resolve().parents[1] / "platform" / "exynos9820"
                  / "patches" / "vendor" / "customize.sh").read_text()
        self.assertIn("$WORK_DIR/vendor/etc/ueventd.rc", source)
        self.assertNotIn("$WORK_DIR/vendor/ueventd.rc", source)

    def test_rejects_duplicate_active_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ueventd.rc"
            line = " ".join(RULE) + "\n"
            path.write_text(line * 2)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                ensure_rule(path)


if __name__ == "__main__":
    unittest.main()
