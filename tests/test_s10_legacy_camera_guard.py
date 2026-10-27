"""Regression tests for the Exynos9820 SamsungCamera legacy feature guard.

The donor's Android 16 map-backed capability model cannot accept the older
field-backed SECOND_PICTURE_CONFIG smali patch. Keep the stock APK intact until
a donor-specific implementation is reviewed.
"""
import os
import subprocess
import unittest


class LegacyCameraGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = subprocess.run(
            ["git", "show", "HEAD:unica/patches/legacy/customize.sh"],
            capture_output=True, text=True, check=True,
        ).stdout
        section = source.index("# Support SECOND_PICTURE_CONFIG camera feature")
        begin = source.index('if [ "$TARGET_PLATFORM_SDK_VERSION" -lt "35" ]; then', section)
        end = source.index("# Support OMX hardware video codecs", begin)
        cls.block = source[begin:end]

    def execute(self, platform, mass_flavor, sdk):
        prelude = (
            'PATCHED=false\n'
            'MODPATH=/tmp/legacy-patches\n'
            'LOG() { printf "LOG:%s\\n" "$1"; }\n'
            'APPLY_PATCH() { printf "PATCH:%s\\n" "$3"; }\n'
        )
        env = os.environ.copy()
        env.update(
            TARGET_PLATFORM=platform,
            TARGET_CAMERA_SUPPORT_MASS_APP_FLAVOR=str(mass_flavor).lower(),
            TARGET_PLATFORM_SDK_VERSION=str(sdk),
        )
        result = subprocess.run(
            ["bash", "-c", prelude + self.block + '\nprintf "PATCHED:%s\\n" "$PATCHED"\n'],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_s10_legacy_camera_preserves_stock(self):
        output = self.execute("exynos9820", False, 31)
        self.assertNotIn("PATCH:", output)
        self.assertIn("PATCHED:false", output)
        self.assertIn("Retaining stock SECOND_PICTURE_CONFIG", output)

    def test_other_legacy_device_retains_standard_backport(self):
        output = self.execute("exynos990", False, 31)
        self.assertIn("PATCH:/tmp/legacy-patches/camera/SamsungCamera.apk/", output)
        self.assertIn("PATCHED:true", output)

    def test_mass_camera_flavor_retains_its_patch(self):
        output = self.execute("exynos9820", True, 31)
        self.assertIn("PATCH:/tmp/legacy-patches/camera_mass/SamsungCamera.apk/", output)
        self.assertIn("PATCHED:true", output)

    def test_modern_sdk_does_not_patch(self):
        output = self.execute("exynos9820", False, 35)
        self.assertNotIn("PATCH:", output)
        self.assertIn("PATCHED:false", output)


if __name__ == "__main__":
    unittest.main()
