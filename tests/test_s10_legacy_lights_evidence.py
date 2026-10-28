#!/usr/bin/env python3
"""Regression checks for complete, fail-closed legacy SehLights donor evidence."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect_s10_legacy_lights_evidence import capture
from collect_s10_virtual_vib_evidence import patch_classes

PATCH = """diff --git a/smali/com/android/server/lights/LightsService$LightImpl.smali b/smali/com/android/server/lights/LightsService$LightImpl.smali
diff --git a/smali_classes2/com/android/server/power/PowerManagerUtil.smali b/smali_classes2/com/android/server/power/PowerManagerUtil.smali
diff --git a/smali/com/android/server/display/LocalDisplayAdapter$BacklightAdapter.smali b/smali/com/android/server/display/LocalDisplayAdapter$BacklightAdapter.smali
diff --git a/smali_classes2/vendor/samsung/hardware/light/ISehLights$Stub$Proxy.smali b/smali_classes2/vendor/samsung/hardware/light/ISehLights$Stub$Proxy.smali
"""
BODY = ".class public Ltest/Donor;\n.method public example()V\n    .locals 0\n    return-void\n.end method\n"


class TestLegacyLightsEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.classes = (*patch_classes(PATCH), "smali/com/android/server/lights/LightsService.smali")
        for rel in self.classes:
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(BODY, encoding="utf-8")

    def test_complete_class_inventory(self):
        evidence = capture(self.root, PATCH)
        self.assertEqual(evidence.count("Complete donor lines:"), 5)
        self.assertIn("return-void", evidence)
        self.assertIn("LightsService$LightImpl.smali", evidence)

    def test_missing_class_fails_closed(self):
        (self.root / self.classes[0]).unlink()
        with self.assertRaisesRegex(ValueError, "missing, ambiguous"):
            capture(self.root, PATCH)

    def test_ambiguous_smali_location_fails_closed(self):
        duplicate = self.root / "smali_classes4" / self.classes[0].split("/", 1)[1]
        duplicate.parent.mkdir(parents=True, exist_ok=True)
        duplicate.write_text(BODY, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            capture(self.root, PATCH)

    def test_unsafe_symlink_fails_closed(self):
        target = self.root / self.classes[0]
        target.unlink()
        target.symlink_to(self.root / self.classes[1])
        with self.assertRaisesRegex(ValueError, "unsafe"):
            capture(self.root, PATCH)

    def test_unterminated_method_fails_closed(self):
        (self.root / self.classes[0]).write_text(".method public broken()V\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unterminated"):
            capture(self.root, PATCH)

    def test_light_hal_signature_probe_is_pipefail_safe(self):
        # grep -q can SIGPIPE the hex producer and make a valid match
        # appear absent when the shell enables pipefail.
        import subprocess

        customize = (Path(__file__).resolve().parents[1] /
                     "unica/patches/legacy/customize.sh").read_text(encoding="utf-8")
        section = customize.split("# Support legacy SehLights HAL", 1)[1].split(
            "# Ensure config_num_physical_slots", 1)[0]
        self.assertIn('xxd -p -c 4 "$WORK_DIR/vendor/bin/hw/vendor.samsung.hardware.light-service" | grep "1853$" >/dev/null', section)
        self.assertNotIn('grep -q "1853$"', section)

        emitter = 'import sys;sys.stdout.write("00001853\\n" + "00000000\\n" * 100000)'
        command = "set -o pipefail; python3 -c " + repr(emitter) + " | grep '1853$' >/dev/null"
        result = subprocess.run(["bash", "-c", command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_actual_patch_has_expected_classes(self):
        patch = (Path(__file__).resolve().parents[1] /
                 "unica/patches/legacy/lights/services.jar/0001-Backport-legacy-SehLights-HAL-code.patch")
        names = patch_classes(patch.read_text(encoding="utf-8"))
        self.assertEqual(len(names), 4)
        self.assertTrue(any("LightsService$LightImpl" in name for name in names))
        self.assertTrue(any("PowerManagerUtil" in name for name in names))


if __name__ == "__main__":
    unittest.main()
