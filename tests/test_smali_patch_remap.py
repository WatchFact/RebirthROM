#!/usr/bin/env python3
"""Regression tests for safe dex-directory remapping of SamsungCamera patches."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("remap_smali_patch", ROOT / "scripts/remap_smali_patch.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

PATCH = """diff --git a/smali_classes3/com/samsung/Test.smali b/smali_classes3/com/samsung/Test.smali
--- a/smali_classes3/com/samsung/Test.smali
+++ b/smali_classes3/com/samsung/Test.smali
@@ -1 +1 @@
-old
+new
"""


class SmaliRemappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.class_file = self.root / "smali_classes4/com/samsung/Test.smali"
        self.class_file.parent.mkdir(parents=True)
        self.class_file.write_text("old\n", encoding="utf-8")

    def test_relocates_headers_without_modifying_hunks(self):
        adjusted = MODULE.remap(self.root, PATCH)
        self.assertEqual(adjusted.count("smali_classes4/com/samsung/Test.smali"), 4)
        self.assertIn("@@ -1 +1 @@\n-old\n+new\n", adjusted)
        patch_path = self.root / "adjusted.patch"
        patch_path.write_text(adjusted, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "apply", "--check", str(patch_path)], check=True)
        subprocess.run(["git", "-C", str(self.root), "apply", str(patch_path)], check=True)
        self.assertEqual(self.class_file.read_text(encoding="utf-8"), "new\n")

    def test_multiple_classes_relocate_independently(self):
        second = self.root / "smali_classes6/com/samsung/Other.smali"
        second.parent.mkdir(parents=True)
        second.write_text("alpha\n", encoding="utf-8")
        extra = """diff --git a/smali_classes4/com/samsung/Other.smali b/smali_classes4/com/samsung/Other.smali
--- a/smali_classes4/com/samsung/Other.smali
+++ b/smali_classes4/com/samsung/Other.smali
@@ -1 +1 @@
-alpha
+beta
"""
        adjusted = MODULE.remap(self.root, PATCH + extra)
        self.assertIn("smali_classes4/com/samsung/Test.smali", adjusted)
        self.assertIn("smali_classes6/com/samsung/Other.smali", adjusted)
        patch_path = self.root / "two.patch"
        patch_path.write_text(adjusted, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "apply", "--check", str(patch_path)], check=True)
        subprocess.run(["git", "-C", str(self.root), "apply", str(patch_path)], check=True)
        self.assertEqual(self.class_file.read_text(), "new\n")
        self.assertEqual(second.read_text(), "beta\n")

    def test_relocation_does_not_hide_incompatible_hunks(self):
        adjusted = MODULE.remap(self.root, PATCH.replace("-old", "-not-the-donor"))
        patch_path = self.root / "incompatible.patch"
        patch_path.write_text(adjusted, encoding="utf-8")
        result = subprocess.run(
            ["git", "-C", str(self.root), "apply", "--check", str(patch_path)],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.class_file.read_text(), "old\n")

    def test_missing_class_fails_closed(self):
        self.class_file.unlink()
        with self.assertRaisesRegex(ValueError, "found 0"):
            MODULE.remap(self.root, PATCH)

    def test_ambiguous_class_fails_closed(self):
        duplicate = self.root / "smali_classes5/com/samsung/Test.smali"
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text("old\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "found 2"):
            MODULE.remap(self.root, PATCH)

    def test_unsafe_paths_fail_closed(self):
        unsafe = PATCH.replace("smali_classes3/com/samsung/Test.smali", "smali_classes3/../Test.smali")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            MODULE.remap(self.root, unsafe)


if __name__ == "__main__":
    unittest.main()
