#!/usr/bin/env python3
"""Regression tests for bounded, read-only SamsungCamera evidence capture."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("collector", Path(__file__).resolve().parents[1] / "scripts/collect_s10_camera_evidence.py")
COLLECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COLLECTOR)


class CameraEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.relative = "com/samsung/android/camera/core2/maker/AutoBeautyPhotoMaker.smali"
        self.first = self.root / "smali_classes2" / self.relative
        self.first.parent.mkdir(parents=True)
        self.source = ".class public Lx;\n.method private foo(Lcom/samsung/android/camera/core2/callback/SceneDetectionEventCallback;)V\n    return-void\n.end method\n"
        self.first.write_text(self.source)

    def test_extracts_only_bounded_matching_method(self):
        report = COLLECTOR.capture(self.root)
        self.assertIn("Matching methods: 1", report)
        self.assertIn("AutoBeautyPhotoMaker.smali", report)
        self.assertEqual(self.first.read_text(), self.source)

    def test_reports_missing_and_ambiguous_classes(self):
        self.first.unlink()
        self.assertIn("Expected one class; found 0", COLLECTOR.capture(self.root))
        self.first.write_text(self.source)
        second = self.root / "smali_classes3" / self.relative
        second.parent.mkdir(parents=True)
        second.write_text(self.source)
        self.assertIn("Expected one class; found 2", COLLECTOR.capture(self.root))

    def test_rejects_missing_decoded_apk(self):
        with self.assertRaises(ValueError):
            COLLECTOR.capture(self.root / "absent")


if __name__ == "__main__":
    unittest.main()
