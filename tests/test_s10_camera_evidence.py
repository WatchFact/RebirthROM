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

    def test_finds_obfuscated_scene_node_callback(self):
        self.first.write_text(".class public Lx;\n.method private a()V\n"
                              "    iget-object v0, p0, Lx;->S1:Lcom/samsung/android/camera/core2/node/sceneDetection/SceneDetectionNodeBase;\n"
                              "    return-void\n.end method\n")
        report = COLLECTOR.capture(self.root)
        self.assertIn("Matching methods: 1", report)
        self.assertIn("->S1:Lcom/samsung/android/camera/core2/node/sceneDetection/SceneDetectionNodeBase;", report)

    def test_bounded_method_count_and_length(self):
        method = (".method private a()V\n" + "    nop\n" * 200
                  + "    iget-object v0, p0, Lx;->S1:Lcom/samsung/android/camera/core2/node/sceneDetection/SceneDetectionNodeBase;\n"
                  + "    return-void\n.end method\n")
        self.first.write_text(".class public Lx;\n" + method * 12)
        report = COLLECTOR.capture(self.root)
        self.assertIn("Matching methods: 12", report)
        self.assertEqual(report.count("Method: .method private a()V"), COLLECTOR.MAX_METHODS)
        self.assertLess(len(report.splitlines()), 42 + COLLECTOR.MAX_METHODS * (COLLECTOR.MAX_METHOD_LINES + 2) + 50)

    def test_reports_missing_and_ambiguous_classes(self):
        self.first.unlink()
        self.assertIn("Expected one class; found 0", COLLECTOR.capture(self.root))
        self.first.write_text(self.source)
        second = self.root / "smali_classes3" / self.relative
        second.parent.mkdir(parents=True)
        second.write_text(self.source)
        self.assertIn("Expected one class; found 2", COLLECTOR.capture(self.root))


    def test_captures_scene_node_callback_implementers(self):
        callback = self.first.parent / "AutoBeautyPhotoMaker$6.smali"
        source = (".class Lx;\n"
                  ".implements Lcom/samsung/android/camera/core2/node/sceneDetection/SceneDetectionNodeBase$NodeCallback;\n"
                  ".method public a(I[J)V\n    return-void\n.end method\n")
        callback.write_text(source)
        unrelated = self.first.parent / "AutoBeautyPhotoMaker$5.smali"
        unrelated.write_text(".class Ly;\n.implements Lother/Interface;\n")
        report = COLLECTOR.capture(self.root)
        self.assertIn("SceneDetectionNodeBase callback implementers: 1", report)
        self.assertIn("AutoBeautyPhotoMaker$6.smali", report)
        self.assertNotIn("AutoBeautyPhotoMaker$5.smali", report)
        self.assertEqual(callback.read_text(), source)

    def test_bounds_anonymous_callback_evidence(self):
        for index in range(16):
            path = self.first.parent / f"AutoBeautyPhotoMaker${index}.smali"
            path.write_text(
                ".class Lx;\n"
                ".implements Lcom/samsung/android/camera/core2/node/sceneDetection/SceneDetectionNodeBase$NodeCallback;\n"
                + "    nop\n" * 500
            )
        report = COLLECTOR.capture(self.root)
        self.assertIn("SceneDetectionNodeBase callback implementers: 16", report)
        self.assertEqual(report.count("Truncated after 220 lines"), 12)
        self.assertLess(len(report.splitlines()), 3000)

    def test_rejects_missing_decoded_apk(self):
        with self.assertRaises(ValueError):
            COLLECTOR.capture(self.root / "absent")


if __name__ == "__main__":
    unittest.main()
