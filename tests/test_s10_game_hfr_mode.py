"""Regression coverage for Android 16 Samsung GameManager VRR method relocation."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/internal/patch_s10_game_hfr_mode.sh"
BASE = "system/framework/gamemanager.jar/smali/com/samsung/android/game/"
METHOD = ".method public isVariableRefreshRateSupported()Ljava/lang/String;\n    const-string v0, \"3\"\n    return-object v0\n.end method\n"


class GameHfrModeTests(unittest.TestCase):
    def run_case(self, *, legacy=True, relocated=True, platform="exynos9820", sdk="36",
                 wrong_legacy_class=False, wrong_relocated_class=False,
                 wrong_relocated_signature=False):
        with tempfile.TemporaryDirectory() as temp:
            old = Path(temp) / (BASE + "GameManagerService.smali")
            new = Path(temp) / (BASE + "VrrManager.smali")
            old.parent.mkdir(parents=True)
            old.write_text(
                ".class public Lcom/samsung/android/game/" +
                ("NotGameManagerService" if wrong_legacy_class else "GameManagerService") + ";\n" +
                (METHOD if legacy else ".method public unrelated()V\n.end method\n"),
                encoding="utf-8")
            if relocated:
                new.write_text(
                    ".class public Lcom/samsung/android/game/" +
                    ("Other" if wrong_relocated_class else "VrrManager") + ";\n" +
                    (METHOD.replace("Ljava/lang/String;", "Z") if wrong_relocated_signature else METHOD),
                    encoding="utf-8")
            env = dict(os.environ, APKTOOL_DIR=temp, TARGET_PLATFORM=platform,
                       SOURCE_PLATFORM_SDK_VERSION=sdk)
            code = r'''
source "$1"
SMALI_PATCH() { printf 'PATCH:%s:%s:%s\n' "$3" "$5" "$6"; }
LOG() { printf 'LOG:%s\n' "$*"; }
ABORT() { printf 'ABORT:%s\n' "$*" >&2; return 1; }
PATCH_S10_GAME_HFR_MODE 3 0
'''
            return subprocess.run(["bash", "-e", "-c", code, "test", str(HELPER)],
                                  capture_output=True, text=True, env=env)

    def test_relocated_android16_method_is_patched(self):
        result = self.run_case(legacy=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PATCH:smali/com/samsung/android/game/VrrManager.smali", result.stdout)
        self.assertIn("relocated", result.stdout)

    def test_existing_legacy_method_keeps_original_path(self):
        result = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PATCH:smali/com/samsung/android/game/GameManagerService.smali", result.stdout)

    def test_missing_relocated_class_fails_closed(self):
        result = self.run_case(legacy=False, relocated=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing or incompatible", result.stderr)

    def test_wrong_relocated_class_fails_closed(self):
        result = self.run_case(legacy=False, wrong_relocated_class=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing or incompatible", result.stderr)

    def test_wrong_relocated_method_signature_fails_closed(self):
        result = self.run_case(legacy=False, wrong_relocated_signature=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lacks exact VRR method", result.stderr)

    def test_wrong_original_class_fails_closed(self):
        result = self.run_case(wrong_legacy_class=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing or incompatible", result.stderr)

    def test_older_sdk_uses_legacy_patch(self):
        result = self.run_case(legacy=False, relocated=False, sdk="35")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PATCH:smali/com/samsung/android/game/GameManagerService.smali", result.stdout)

    def test_other_platform_uses_legacy_patch(self):
        result = self.run_case(legacy=False, relocated=False, platform="exynos990")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PATCH:smali/com/samsung/android/game/GameManagerService.smali", result.stdout)


if __name__ == "__main__":
    unittest.main()
