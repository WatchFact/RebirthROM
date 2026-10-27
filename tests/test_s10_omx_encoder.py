"""Verify donor-specific optional OMX encoder lookup without weakening bytecode checks."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "unica/patches/legacy/customize.sh"
APK = "system/priv-app/SamsungCamera/SamsungCamera.apk"
CLASS = "com/samsung/android/sum/core/filter/EncoderFilter.smali"


class S10OmxEncoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index("PATCH_S10_OMX_ENCODER()\n{")
        end = source.index("# Support OMX hardware video codecs", start)
        cls.function = source[start:end]
        cls.source = source

    def run_case(self, directories=(), fail_patch=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "system" / "priv-app" / "SamsungCamera" / "SamsungCamera.apk"
            root.mkdir(parents=True)
            for directory in directories:
                file = root / directory / CLASS
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(".method public configCodec(Lcom/samsung/android/sum/core/message/Message;)V\n.end method\n")
            shell = (
                'LOG() { printf "LOG:%s\n" "$1"; }\n'
                'ABORT() { printf "ABORT:%s\n" "$1" >&2; return 1; }\n'
                'DECODE_APK() { printf "DECODE:%s\n" "$2"; }\n'
                'SMALI_PATCH() { printf "PATCH:%s|%s|%s\n" "$2" "$3" "$6"; '
                '[ "${FAIL_PATCH:-0}" != 1 ]; }\n'
                + self.function
                + '\nPATCH_S10_OMX_ENCODER "' + APK + '" v4\n'
            )
            env = os.environ.copy()
            env.update(APKTOOL_DIR=temporary, FAIL_PATCH="1" if fail_patch else "0")
            return subprocess.run(["bash", "-c", shell], env=env, capture_output=True, text=True)

    def test_missing_class_is_not_a_patch_target(self):
        result = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No EncoderFilter class", result.stdout)
        self.assertNotIn("PATCH:", result.stdout)

    def test_relocated_class_uses_actual_dex_directory(self):
        result = self.run_case(("smali_classes4",))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PATCH:" + APK + "|smali_classes4/" + CLASS + "|const v4, 0x7f420888", result.stdout)

    def test_original_class_path_still_works(self):
        result = self.run_case(("smali",))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("|smali/" + CLASS + "|", result.stdout)

    def test_ambiguous_class_fails_closed(self):
        result = self.run_case(("smali", "smali_classes4"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ambiguous EncoderFilter", result.stderr)
        self.assertNotIn("PATCH:", result.stdout)

    def test_present_incompatible_class_propagates_patch_failure(self):
        result = self.run_case(("smali_classes4",), fail_patch=True)
        self.assertNotEqual(result.returncode, 0)

    def test_other_platforms_keep_original_compatibility_patch(self):
        self.assertIn('"smali_classes3/com/samsung/android/sum/core/filter/EncoderFilter.smali" "replace"', self.source)
        self.assertIn('if [[ "$TARGET_PLATFORM" == "exynos9820" ]]; then\n            PATCH_S10_OMX_ENCODER', self.source)


if __name__ == "__main__":
    unittest.main()
