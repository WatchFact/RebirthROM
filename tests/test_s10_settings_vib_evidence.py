#!/usr/bin/env python3
"""Fail-closed tests for full donor Settings smali diagnostics."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("settings_vib", ROOT / "scripts/collect_s10_settings_vib_evidence.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

PATCH = "diff --git a/smali_classes4/com/samsung/Test.smali b/smali_classes4/com/samsung/Test.smali\n"
DONOR = ".class public Lcom/samsung/Test;\n.super Ljava/lang/Object;\n.method public foo()V\n    return-void\n.end method\n"


class SettingsVibrationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cls = self.root / "smali_classes5/com/samsung/Test.smali"
        self.cls.parent.mkdir(parents=True)
        self.cls.write_text(DONOR)

    def test_complete_relocated_donor_class(self):
        report = MODULE.capture(self.root, PATCH)
        self.assertIn("smali_classes5/com/samsung/Test.smali", report)
        self.assertIn(DONOR.rstrip(), report)
        self.assertIn("sha256=", report)
        self.assertIn("END smali_classes5", report)

    def test_missing_class_rejected(self):
        self.cls.unlink()
        with self.assertRaisesRegex(ValueError, "found 0"):
            MODULE.capture(self.root, PATCH)

    def test_ambiguous_class_rejected(self):
        duplicate = self.root / "smali_classes6/com/samsung/Test.smali"
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text(DONOR)
        with self.assertRaisesRegex(ValueError, "found 2"):
            MODULE.capture(self.root, PATCH)

    def test_incompatible_method_boundaries_rejected(self):
        self.cls.write_text(DONOR.replace(".end method", ""))
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            MODULE.capture(self.root, PATCH)

    def test_unexpected_size_rejected(self):
        self.cls.write_text(DONOR + "#" * (MODULE.MAX_CLASS_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "byte limits"):
            MODULE.capture(self.root, PATCH)

    def test_unsafe_path_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsafe"):
            MODULE.capture(self.root, PATCH.replace("com/samsung/Test.smali", "../Test.smali"))

    def test_duplicate_patch_file_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            MODULE.capture(self.root, PATCH + PATCH)

    def test_unmodified_donor(self):
        MODULE.capture(self.root, PATCH)
        self.assertEqual(self.cls.read_text(), DONOR)


if __name__ == "__main__":
    unittest.main()
