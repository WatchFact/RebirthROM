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

    def test_complete_aidl_method_uses_actual_double_dollar_lambda_name(self):
        # Android 16 donor uses a synthetic class with two dollar signs.
        # A single-dollar anchor silently omits the complete method.
        source = "\n".join([
            ".class public Lx;",
            ".method public final dispatch()V",
            "    .locals 1",
            "    new-instance v0, Lcom/android/server/biometrics/sensors/face/aidl/SemFaceServiceExImpl$$ExternalSyntheticLambda6;",
            "    return-void",
            ".end method",
        ]) + "\n"
        self.source.write_text(source)
        report = COLLECTOR.capture(self.root, PATCH)
        self.assertIn("Complete method evidence at 2:", report)
        self.assertIn("SemFaceServiceExImpl$$ExternalSyntheticLambda6;", report)
        self.assertIn("6: .end method", report)
        self.assertEqual(self.source.read_text(), source)

    def test_captures_complete_ontransact_method_for_exact_rebase(self):
        rel = ("com/android/server/biometrics/sensors/face/hidl/"
               "HidlToAidlCallbackConverter.smali")
        path = self.root / "smali" / rel
        path.parent.mkdir(parents=True)
        method = (".class public Lx;\n"
                  ".method public final onTransact(ILandroid/os/HwParcel;)V\n"
                  "    .locals 2\n"
                  + "    nop\n" * 350
                  + "    return-void\n.end method\n")
        path.write_text(method)
        patch = ("diff --git a/smali/" + rel + " b/smali/" + rel + "\n")
        report = COLLECTOR.capture(self.root, patch)
        self.assertIn("Complete method evidence at 2:", report)
        self.assertIn("355: .end method", report)
        self.assertEqual(path.read_text(), method)

    def test_captures_android16_face_authentication_method_without_legacy_log(self):
        # The verified Android 16 donor has semDoAuthenticate(), not
        # the obsolete "authenticate BILG" log string.
        rel = ("com/android/server/biometrics/sensors/face/aidl/"
               "FaceAuthenticationClient.smali")
        path = self.root / "smali" / rel
        path.parent.mkdir(parents=True)
        method = (".class public Lx;\n"
                  ".method public final semDoAuthenticate()V\n"
                  "    .locals 17\n"
                  + "    nop\n" * 788
                  + "    return-void\n.end method\n")
        path.write_text(method)
        patch = ("diff --git a/smali/" + rel + " b/smali/" + rel + "\n")
        report = COLLECTOR.capture(self.root, patch)
        self.assertIn("Complete method evidence at 2:", report)
        self.assertIn(".method public final semDoAuthenticate()V", report)
        self.assertIn("793: .end method", report)
        self.assertEqual(path.read_text(), method)

    def test_rejects_oversized_full_method_without_unbounded_dump(self):
        rel = ("com/android/server/biometrics/sensors/face/hidl/"
               "TestHal.smali")
        path = self.root / "smali" / rel
        path.parent.mkdir(parents=True)
        path.write_text(".class public Lx;\n"
                        ".method public onTransact()V\n"
                        + "    nop\n" * 2000
                        + "    return-void\n.end method\n")
        patch = ("diff --git a/smali/" + rel + " b/smali/" + rel + "\n")
        report = COLLECTOR.capture(self.root, patch)
        self.assertIn("Method exceeds 1600 lines; not exported", report)
        self.assertLess(len(report.splitlines()), 400)

    def test_opt_in_full_class_evidence_is_bounded_and_read_only(self):
        # The full Android 16 class context is required for an exact patch
        # rebase, but must not leak unrelated or unbounded decoded classes.
        source = (".class public Lx;\\n" + "    nop\\n" * 120 +
                  ".method public final onEnrollmentProgress(II)V\\n" +
                  "    return-void\\n.end method\\n")
        self.source.write_text(source)
        default = COLLECTOR.capture(self.root, PATCH)
        self.assertNotIn("Complete class evidence:", default)
        report = COLLECTOR.capture(self.root, PATCH, full_classes=True)
        self.assertIn("Complete class evidence: AidlResponseHandler.smali", report)
        self.assertIn("124: .end method", report)
        self.assertEqual(self.source.read_text(), source)

    def test_full_class_limit_rejects_oversized_donor(self):
        source = ".class public Lx;\\n" + "    nop\\n" * 2600
        self.source.write_text(source)
        report = COLLECTOR.capture(self.root, PATCH, full_classes=True)
        self.assertIn("Full class exceeds 2500 lines; not exported", report)
        self.assertNotIn("Complete class evidence:", report)
        self.assertLess(len(report.splitlines()), 120)
        self.assertEqual(self.source.read_text(), source)

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
