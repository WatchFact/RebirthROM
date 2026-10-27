"""Fail-closed regression tests for the Android-16 S10 camera bridge."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import backport_s10_scene_detection as bridge


FORWARDER = """.class public Lcom/samsung/android/camera/core2/callback/forwarder/TextDetectionInfoCallbackForwarder;
.super Ljava/lang/Object;
.implements Lcom/samsung/android/camera/core2/callback/TextDetectionInfoCallback;

# direct methods
.method public constructor <init>()V
    .locals 0
    return-void
.end method
"""
MANAGER = f""".class public Lcom/samsung/android/camera/core2/maker/MakerCallbackManager;
.super Ljava/lang/Object;
{bridge.SEND_SIGNATURE}
    .locals 2
    sget-object v1, Lcom/samsung/android/camera/core2/local/vendorkey/SemCaptureResult;->y1:Landroid/hardware/camera2/CaptureResult$Key;
    check-cast p3, Ljava/lang/Integer;
    invoke-interface {{v0, p2, p3, p1}}, Lcom/samsung/android/camera/core2/callback/TextDetectionInfoCallback;->onTextDetectionInfo(Ljava/lang/Long;Ljava/lang/Integer;Lcom/samsung/android/camera/core2/CamDevice;)V
    return-void
.end method
"""
CALLBACK = """.class Lcom/samsung/android/camera/core2/maker/Example;
.super Ljava/lang/Object;
.implements Lcom/samsung/android/camera/core2/node/sceneDetection/SceneDetectionNodeBase$NodeCallback;
.method public a(I[J)V
    .locals 2
    invoke-virtual {v0}, Lcom/samsung/android/camera/core2/maker/MakerCallbackManager;->getSceneDetectionEventCallback()Lcom/samsung/android/camera/core2/callback/SceneDetectionEventCallback;
    return-void
.end method
"""


class SceneBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.files = {}
        values = {bridge.FORWARDER: FORWARDER, bridge.MANAGER: MANAGER}
        values.update({f"maker/{name}.smali": CALLBACK for name in bridge.CALLBACKS})
        for name, content in values.items():
            path = self.root / "smali_classes2" / bridge.PREFIX / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            self.files[name] = path

    def test_exact_donor_adaptation_and_no_repeat(self):
        edited = bridge.adapt(self.root)
        self.assertEqual(len(edited), 7)
        self.assertIn("volatile sceneDetectionEvent:I", self.files[bridge.FORWARDER].read_text())
        manager = self.files[bridge.MANAGER].read_text()
        self.assertIn(":rebirth_scene_done", manager)
        self.assertIn("    .locals 3", manager)
        self.assertIn("    const/4 v2, 0x2", manager)
        self.assertNotIn("    const/4 v0, 0x2", manager)
        for name in bridge.CALLBACKS:
            self.assertIn("sput p1", self.files[f"maker/{name}.smali"].read_text())
        with self.assertRaises(ValueError):
            bridge.adapt(self.root)

    def test_missing_callback_rejects_without_writes(self):
        self.files[f"maker/{bridge.CALLBACKS[-1]}.smali"].unlink()
        originals = {p: p.read_bytes() for p in self.files.values() if p.exists()}
        with self.assertRaises(ValueError):
            bridge.adapt(self.root)
        self.assertEqual(originals, {p: p.read_bytes() for p in originals})

    def test_unknown_capture_key_rejects_without_writes(self):
        p = self.files[bridge.MANAGER]
        p.write_text(p.read_text().replace("->y1:", "->other:"), encoding="utf-8")
        originals = {p: p.read_bytes() for p in self.files.values()}
        with self.assertRaises(ValueError):
            bridge.adapt(self.root)
        self.assertEqual(originals, {p: p.read_bytes() for p in originals})

    def test_duplicate_class_rejected(self):
        original = self.files[bridge.FORWARDER]
        second = self.root / "smali_classes3" / bridge.PREFIX / bridge.FORWARDER
        second.parent.mkdir(parents=True, exist_ok=True)
        second.write_bytes(original.read_bytes())
        with self.assertRaises(ValueError):
            bridge.adapt(self.root)


if __name__ == "__main__":
    unittest.main()
