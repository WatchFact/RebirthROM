#!/usr/bin/env python3
"""Tests for read-only, bounded S10 face patch diagnostics."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "face_evidence", Path(__file__).resolve().parents[1] /
    "scripts/collect_s10_face_evidence.py")
COLLECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COLLECTOR)

PATCH = ("diff --git a/smali/com/android/server/biometrics/sensors/face/"
         "aidl/AidlResponseHandler.smali b/smali/com/android/server/"
         "biometrics/sensors/face/aidl/AidlResponseHandler.smali\n")
REL = "com/android/server/biometrics/sensors/face/aidl/AidlResponseHandler.smali"


class FaceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "smali_classes2" / REL
        self.source.parent.mkdir(parents=True)
        self.original = (
            ".class public Lx;\n"
            ".method public onAuthentication()V\n"
            "    iget-object v0, p0, Lx;->mHandlerMain:Landroid/os/Handler;\n"
            "    return-void\n"
            ".end method\n"
        )
        self.source.write_text(self.original)

    def test_locates_class_across_smali_directories_without_writing(self):
        report = COLLECTOR.capture(self.root, PATCH)
        self.assertIn("Actual path: smali_classes2/", report)
        self.assertIn("Matching methods: 1", report)
        self.assertIn("mHandlerMain", report)
        self.assertEqual(self.source.read_text(), self.original)

    def test_missing_and_ambiguous_classes_fail_visibly(self):
        self.source.unlink()
        self.assertIn("Matching decoded classes: 0", COLLECTOR.capture(self.root, PATCH))
        self.source.write_text(self.original)
        duplicate = self.root / "smali_classes3" / REL
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text(self.original)
        self.assertIn("Matching decoded classes: 2", COLLECTOR.capture(self.root, PATCH))

    def test_bounded_large_method_and_lambda(self):
        self.source.write_text(
            ".class public Lx;\n.method public big()V\n"
            + "    nop\n" * 600
            + "    const-string v0, \"HidlToAidl\"\n"
            + "    nop\n" * 600
            + "    return-void\n.end method\n")
        lam = self.source.parent / "SemFaceServiceExImpl$$ExternalSyntheticLambda8.smali"
        lam.write_text(".class public Ly;\n" + "    nop\n" * 500)
        report = COLLECTOR.capture(self.root, PATCH)
        self.assertIn("Face service synthetic lambda inventory: 1", report)
        self.assertIn("Truncated after 160 lines", report)
        self.assertLess(len(report.splitlines()), 650)

    def test_patch_parser_rejects_empty_and_unsafe_paths(self):
        with self.assertRaises(ValueError):
            COLLECTOR.patch_classes("not a diff")
        bad = ("diff --git a/smali/../evil.smali "
               "b/smali/../evil.smali\n")
        with self.assertRaises(ValueError):
            COLLECTOR.patch_classes(bad)

    def test_missing_decoded_services_is_rejected(self):
        with self.assertRaises(ValueError):
            COLLECTOR.capture(self.root / "missing", PATCH)


if __name__ == "__main__":
    unittest.main()
