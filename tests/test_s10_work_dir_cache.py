"""Exercise work-directory cache decisions without running a firmware build."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "scripts/make_rom.sh").read_text()
START = "# A completed work tree can be reused only when the caller explicitly opts"
assert START in SOURCE
SNIPPET = SOURCE.split(START, 1)[1].split("\ntrap 'PRINT_BUILD_OUTCOME' EXIT", 1)[0]


class WorkDirectoryCacheTests(unittest.TestCase):
    def run_case(self, *, cache=True, force=False, marker="same", vendor=True,
                 extracted=True):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            work = root / "work"
            work.mkdir()
            (work / ".completed").write_text(marker)
            system = work / "system/system"
            system.mkdir(parents=True)
            (system / "build.prop").write_text("ro.build.id=test\n")
            vendor_dir = work / "vendor"
            vendor_dir.mkdir()
            if vendor:
                (vendor_dir / "build.prop").write_text("ro.vendor.build.id=test\n")
            fw = root / "firmware"
            for name in ("source", "target"):
                path = fw / name
                path.mkdir(parents=True)
                if extracted:
                    (path / ".extracted").touch()
            env = dict(os.environ, WORK_DIR=str(work), FW_DIR=str(fw),
                       SOURCE_FIRMWARE_PATH="source", TARGET_FIRMWARE_PATH="target",
                       FORCE=str(force).lower(), USE_APK_CACHE=str(cache).lower())
            command = ("set -euo pipefail\n"
                       "GET_WORK_DIR_HASH() { printf 'same\\n'; }\n"
                       "LOG() { :; }\nLOGW() { :; }\n"
                       + SNIPPET + "\nprintf '%s' \"$BUILD_ROM\"\n")
            result = subprocess.run(["bash", "-c", command], env=env,
                                    capture_output=True, text=True, check=True)
            return result.stdout, work.exists()

    def test_reuses_only_complete_matching_explicit_cache(self):
        self.assertEqual(self.run_case(), ("false", True))

    def test_force_and_no_cache_always_clean(self):
        for kwargs in ({"force": True}, {"cache": False}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.run_case(**kwargs), ("true", False))

    def test_incomplete_or_changed_tree_is_cleaned(self):
        for kwargs in ({"marker": "stale"}, {"vendor": False},
                       {"extracted": False}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.run_case(**kwargs), ("true", False))


if __name__ == "__main__":
    unittest.main()
