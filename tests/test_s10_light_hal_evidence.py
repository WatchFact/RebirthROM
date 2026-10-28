"""Regression tests for read-only light HAL init/VINTF evidence."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect_s10_light_hal_evidence import inspect_root


class LightEvidenceTests(unittest.TestCase):
    def test_finds_generic_init_service_and_manifest_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init = root / "vendor/etc/init/init.vendor.rc"
            init.parent.mkdir(parents=True)
            init.write_text("service lights /vendor/bin/hw/vendor.samsung.hardware.light-service\n")
            manifest = root / "vendor/etc/vintf/manifest/vendor.xml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("<name>android.hardware.light</name>\n")
            result = inspect_root(root)
            self.assertEqual(len(result["matches"]), 2)
            self.assertEqual({m["path"] for m in result["matches"]},
                             {"vendor/etc/init/init.vendor.rc", "vendor/etc/vintf/manifest/vendor.xml"})
            self.assertEqual(result["light_service_binary"], "not found")

    def test_binary_presence_is_not_claimed_as_bootability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "vendor/bin/hw/vendor.samsung.hardware.light-service"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"ELF-not-a-real-binary")
            result = inspect_root(root)
            self.assertEqual(result["light_service_binary"], "present")
            self.assertEqual(result["matches"], [])

    def test_rejects_symlinked_binary_and_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vendor/etc/init").mkdir(parents=True)
            (root / "vendor/etc/init/light.rc").symlink_to("/etc/passwd")
            (root / "vendor/bin/hw").mkdir(parents=True)
            (root / "vendor/bin/hw/vendor.samsung.hardware.light-service").symlink_to("/etc/passwd")
            result = inspect_root(root)
            self.assertEqual(result["light_service_binary"], "symlink (not followed)")
            self.assertEqual(result["matches"], [])

    def test_missing_root_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_root(Path(tmp) / "absent")
            self.assertFalse(result["root_exists"])
            self.assertEqual(result["matches"], [])

    def test_workflow_captures_evidence_on_failed_build(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/compile-s10.yml").read_text()
        self.assertIn("collect_s10_light_hal_evidence.py", workflow)
        self.assertIn("out/fw/SM-G975F_AUT", workflow)
        self.assertIn("out/target/beyond2lte/work_dir", workflow)


    def test_reports_actual_aidl_manifest_and_init_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init = root / "vendor/etc/init/lights-default-sec.rc"
            init.parent.mkdir(parents=True)
            init.write_text(
                "service vendor.samsung.hardware.light-default "
                "/vendor/bin/hw/vendor.samsung.hardware.light-service\n"
                "    class hal\n"
                "    interface aidl android.hardware.light.ILights/default\n"
            )
            manifest = root / "vendor/etc/vintf/manifest/lights-default-sec.xml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                '<manifest version="1.0" type="device">'
                '<hal format="aidl"><name>android.hardware.light</name>'
                '<version>1</version><interface><name>ILights</name>'
                '<instance>default</instance></interface></hal></manifest>'
            )
            result = inspect_root(root)
            self.assertEqual(result["hal_declarations"][0]["format"], "aidl")
            self.assertEqual(result["hal_declarations"][0]["versions"], ["1"])
            self.assertEqual(result["hal_declarations"][0]["interfaces"],
                             [{"name": "ILights", "instances": ["default"]}])
            self.assertEqual(result["init_services"][0]["name"],
                             "vendor.samsung.hardware.light-default")
            self.assertEqual(result["init_services"][0]["interfaces"],
                             ["aidl android.hardware.light.ILights/default"])
            self.assertEqual(result["parse_errors"], [])

    def test_reports_hidl_manifest_without_guessing_aidl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "vendor/etc/vintf/manifest/lights.xml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                '<manifest version="1.0" type="device">'
                '<hal format="hidl"><name>android.hardware.light</name>'
                '<transport>hwbinder</transport><version>2.0</version>'
                '<interface><name>ILight</name><instance>default</instance>'
                '</interface></hal></manifest>'
            )
            result = inspect_root(root)
            self.assertEqual(result["hal_declarations"][0]["format"], "hidl")
            self.assertEqual(result["hal_declarations"][0]["transport"], ["hwbinder"])

    def test_invalid_vintf_xml_is_reported_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "vendor/etc/vintf/manifest/lights.xml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("<manifest><hal><name>android.hardware.light</name>")
            result = inspect_root(root)
            self.assertEqual(result["hal_declarations"], [])
            self.assertEqual(len(result["parse_errors"]), 1)
            self.assertIn("ParseError", result["parse_errors"][0]["error"])


if __name__ == "__main__":
    unittest.main()
