"""Regression tests for the Android 16 diagnostic-only HFR smali guard."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/internal/patch_refresh_rate_dump.sh"
REL = "system/framework/framework.jar/smali_classes6/com/samsung/android/hardware/display/RefreshRateConfig.smali"
CLASS = ".class public Lcom/samsung/android/hardware/display/RefreshRateConfig;\\n"
DUMP = ".method public dump(Ljava/io/PrintWriter;Ljava/lang/String;Z)V\\n    return-void\\n.end method\\n"


class RefreshRateDumpTests(unittest.TestCase):
    def run_case(self, body=None, *, platform="exynos9820", sdk="36"):
        with tempfile.TemporaryDirectory() as temp:
            if body is not None:
                file = Path(temp) / REL
                file.parent.mkdir(parents=True)
                file.write_text(body, encoding="utf-8")
            env = dict(os.environ, APKTOOL_DIR=temp, TARGET_PLATFORM=platform,
                       SOURCE_PLATFORM_SDK_VERSION=sdk)
            code = """
source "$1"
SMALI_PATCH() { printf 'PATCH:%s\\n' "$5"; }
LOG() { printf 'SKIP:%s\\n' "$*"; }
ABORT() { printf 'ABORT:%s\\n' "$*" >&2; return 1; }
PATCH_REFRESH_RATE_DUMP 'HFR_DEFAULT_REFRESH_RATE: 120' 'HFR_DEFAULT_REFRESH_RATE: 60'
"""
            return subprocess.run(["bash", "-e", "-c", code, "test", str(HELPER)],
                                  capture_output=True, text=True, env=env)

    def test_android16_without_legacy_dump_skips_only_diagnostic(self):
        result = self.run_case(CLASS + ".method public getMainInstance()V\\n.end method\\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SKIP:", result.stdout)
        self.assertNotIn("PATCH:", result.stdout)

    def test_android16_with_legacy_dump_retains_patch(self):
        result = self.run_case(CLASS + DUMP)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PATCH:dump(", result.stdout)

    def test_unrelated_method_name_does_not_count(self):
        result = self.run_case(CLASS + ".method public not_dump(Ljava/io/PrintWriter;Ljava/lang/String;Z)V\\n.end method\\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SKIP:", result.stdout)

    def test_missing_decoded_class_is_rejected(self):
        result = self.run_case()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing decoded", result.stderr)

    def test_wrong_class_declaration_is_rejected(self):
        result = self.run_case(".class public Lcom/example/Unrelated;\\n" + DUMP)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected RefreshRateConfig", result.stderr)

    def test_legacy_sdk_retains_old_patch_path(self):
        result = self.run_case(None, sdk="35")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PATCH:dump(", result.stdout)

    def test_other_platform_retains_old_patch_path(self):
        result = self.run_case(None, platform="exynos990")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PATCH:dump(", result.stdout)


if __name__ == "__main__":
    unittest.main()
