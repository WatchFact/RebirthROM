"""Guard against replacing native S10 light HAL with S21 donor binaries."""
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_s10_stock_light_hal import BINARY, INIT, MANIFEST, verify


class StockLightHalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for relative in (BINARY, INIT, MANIFEST):
            (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
        elf = bytearray(64)
        elf[:6] = b"\x7fELF\x02\x01"
        elf[18:20] = (183).to_bytes(2, "little")
        (self.root / BINARY).write_bytes(elf)
        (self.root / INIT).write_text(
            "service vendor.samsung.hardware.light-default "
            "/vendor/bin/hw/vendor.samsung.hardware.light-service\n"
            "    class hal\n"
        )
        (self.root / MANIFEST).write_text(
            '<manifest version="1.0" type="device"><hal format="aidl">'
            '<name>android.hardware.light</name><fqname>ILights/default</fqname>'
            '</hal></manifest>'
        )

    def test_native_s10_aidl_service_is_accepted(self):
        verify(self.root)

    def test_interface_child_declaration_is_accepted(self):
        (self.root / MANIFEST).write_text(
            '<manifest><hal format="aidl"><name>android.hardware.light</name>'
            '<interface><name>ILights</name><instance>default</instance></interface>'
            '</hal></manifest>'
        )
        verify(self.root)

    def test_missing_native_binary_fails_closed(self):
        (self.root / BINARY).unlink()
        with self.assertRaisesRegex(ValueError, "Missing, empty"):
            verify(self.root)

    def test_symlink_binary_fails_closed(self):
        (self.root / BINARY).unlink()
        (self.root / BINARY).symlink_to("/bin/true")
        with self.assertRaisesRegex(ValueError, "symlinked"):
            verify(self.root)

    def test_wrong_architecture_fails_closed(self):
        blob = bytearray((self.root / BINARY).read_bytes())
        blob[18:20] = (62).to_bytes(2, "little")
        (self.root / BINARY).write_bytes(blob)
        with self.assertRaisesRegex(ValueError, "ARM ELF"):
            verify(self.root)

    def test_wrong_service_path_fails_closed(self):
        (self.root / INIT).write_text(
            "service vendor.samsung.hardware.light-default /vendor/bin/hw/other-service\n"
        )
        with self.assertRaisesRegex(ValueError, "miswired"):
            verify(self.root)

    def test_duplicate_service_fails_closed(self):
        path = self.root / INIT
        path.write_text(path.read_text() * 2)
        with self.assertRaisesRegex(ValueError, "duplicated"):
            verify(self.root)

    def test_hidl_manifest_fails_closed(self):
        path = self.root / MANIFEST
        path.write_text(path.read_text().replace('format="aidl"', 'format="hidl"'))
        with self.assertRaisesRegex(ValueError, "AIDL"):
            verify(self.root)

    def test_malformed_manifest_fails_closed(self):
        (self.root / MANIFEST).write_text("<manifest><hal>")
        with self.assertRaises(ET.ParseError):
            verify(self.root)

    def test_no_cross_device_overlay_in_platform_script(self):
        script = (Path(__file__).resolve().parents[1]
                  / "platform/exynos9820/patches/vendor/customize.sh").read_text()
        self.assertIn("verify_s10_stock_light_hal.py", script)
        self.assertNotIn('ADD_TO_WORK_DIR "p3sxxx" "vendor" "bin/hw/vendor.samsung.hardware.light-service"', script)
        self.assertNotIn('ADD_TO_WORK_DIR "p3sxxx" "vendor" "lib64/android.hardware.light', script)


if __name__ == "__main__":
    unittest.main()
