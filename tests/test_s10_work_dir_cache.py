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
                       "GET_WORK_DIR_HASH() { printf 'same\n'; }\n"
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

    def test_work_hash_covers_prebuilts_security_config_and_firmware(self):
        hash_source = SOURCE.split("GET_WORK_DIR_HASH()\n{\n", 1)[1].split(
            "\n}\n\nPREPARE_SCRIPT()", 1)[0]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for directory in ("scripts", "unica", "target/beyond2lte",
                              "platform/exynos9820", "prebuilts/samsung",
                              "security/avb"):
                (root / directory).mkdir(parents=True)
            for name in ("scripts/a.sh", "unica/module.sh",
                         "target/beyond2lte/config.sh", "platform/exynos9820/config.sh",
                         "prebuilts/samsung/blob.so", "security/avb/key.pem",
                         "buildenv.sh", ".gitmodules"):
                (root / name).write_text("original\n")
            env = dict(os.environ, SRC_DIR=str(root),
                       TARGET_CODENAME="beyond2lte", TARGET_PLATFORM="exynos9820",
                       SOURCE_FIRMWARE="SM-S926B/EUX", TARGET_FIRMWARE="SM-G975F/AUT")
            command = ("set -euo pipefail\nLOGE() { :; }\nGET_WORK_DIR_HASH() {\n"
                       + hash_source + "\n}\nGET_WORK_DIR_HASH\n")

            def digest():
                return subprocess.run(["bash", "-c", command], env=env,
                                      capture_output=True, text=True,
                                      check=True).stdout.strip()

            initial = digest()
            self.assertEqual(len(initial), 64)
            for name in ("prebuilts/samsung/blob.so", "security/avb/key.pem",
                         "buildenv.sh", ".gitmodules"):
                path = root / name
                path.write_text("changed\n")
                self.assertNotEqual(initial, digest(), name)
                path.write_text("original\n")
                self.assertEqual(initial, digest(), name)
            env["TARGET_FIRMWARE"] = "SM-G975F/BTU"
            self.assertNotEqual(initial, digest())

            env["TARGET_FIRMWARE"] = "SM-G975F/AUT"
            (root / "security/avb/key.pem").unlink()
            self.assertNotEqual(initial, digest())
            (root / "security").rename(root / "security-missing")
            result = subprocess.run(["bash", "-c", command], env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_completed_marker_requires_valid_input_digest(self):
        # Execute the real completion-marker block in isolation. In particular,
        # command substitution inside echo previously masked a hash failure.
        marker_start = "    # A completed work tree must have a verified input hash."
        marker_block = SOURCE.split(marker_start, 1)[1].split(
            "\nfi\n\nif $BUILD_ZIP", 1)[0]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, hash_body, valid in (
                ("hash-failure", "return 1", False),
                ("invalid-digest", "printf invalid", False),
                ("valid-digest", "printf '%064d' 0", True),
            ):
                with self.subTest(name=name):
                    work = root / name
                    work.mkdir()
                    command = ("set -euo pipefail\n"
                               "LOGE() { :; }\n"
                               "GET_WORK_DIR_HASH() { " + hash_body + "; }\n"
                               + marker_block + "\n")
                    result = subprocess.run(
                        ["bash", "-c", command],
                        env=dict(os.environ, WORK_DIR=str(work)),
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode == 0, valid)
                    self.assertEqual((work / ".completed").exists(), valid)
                    if valid:
                        self.assertEqual((work / ".completed").read_text(), "0" * 64)



if __name__ == "__main__":
    unittest.main()
