#!/usr/bin/env python3
"""Regression tests for the stock S10 AIDL light HAL framework selector."""
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    's10_aidl', Path(__file__).resolve().parents[1] / 'scripts' / 'force_s10_aidl_lights.py')
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TestS10AidlLights(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lights = self.root / 'smali/com/android/server/lights/LightsService.smali'
        self.power = self.root / 'smali_classes2/com/android/server/power/PowerManagerUtil.smali'
        self.lights.parent.mkdir(parents=True)
        self.power.parent.mkdir(parents=True)
        self.lights.write_text('.class Lcom/android/server/lights/LightsService;\n'
                               'Lcom/android/server/power/PowerManagerUtil;->SEC_FEATURE_USE_LIGHTS_HAL_EXTENSION:Z\n'
                               'mVintfLights:Lcom/android/server/lights/LightsService$VintfHalCache;\n'
                               'mVintfSehLights:Lcom/android/server/lights/LightsService$VintfHalCache;\n'
                               'Landroid/hardware/light/ILights$Stub$Proxy;->getLights()\n')
        self.power.write_text('.class Lcom/android/server/power/PowerManagerUtil;\n'
                              '.method static constructor <clinit>()V\n    .locals 17\n'
                              '    :goto_1c\n    sput-boolean v16, '
                              + MOD.FLAG + '\n    return-void\n.end method\n')

    def test_selects_standard_aidl_and_is_idempotent(self):
        self.assertTrue(MOD.patch(self.root))
        content = self.power.read_text()
        self.assertIn('    :goto_1c\n    const/16 v16, 0x0\n\n    sput-boolean v16, ', content)
        self.assertFalse(MOD.patch(self.root))
        self.assertEqual(self.power.read_text(), content)

    def test_missing_standard_aidl_path_rejected(self):
        self.lights.write_text('invalid')
        with self.assertRaisesRegex(ValueError, 'AIDL/SehLights'):
            MOD.patch(self.root)

    def test_missing_class_rejected(self):
        self.power.unlink()
        with self.assertRaisesRegex(ValueError, 'expected one'):
            MOD.patch(self.root)

    def test_ambiguous_class_rejected(self):
        extra = self.root / 'smali_classes3/com/android/server/power/PowerManagerUtil.smali'
        extra.parent.mkdir(parents=True)
        shutil.copyfile(self.power, extra)
        with self.assertRaisesRegex(ValueError, 'expected one'):
            MOD.patch(self.root)

    def test_live_register_rejected(self):
        self.power.write_text(self.power.read_text().replace('    return-void', '    move v0, v16\n    return-void'))
        with self.assertRaisesRegex(ValueError, 'live after'):
            MOD.patch(self.root)

    def test_unexpected_register_layout_rejected(self):
        self.power.write_text(self.power.read_text().replace('.locals 17', '.locals 3'))
        with self.assertRaisesRegex(ValueError, 'register layout'):
            MOD.patch(self.root)

    def test_duplicate_assignment_rejected(self):
        source = self.power.read_text()
        self.power.write_text(source.replace('    return-void', f'    sput-boolean v16, {MOD.FLAG}\n    return-void'))
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            MOD.patch(self.root)

    def test_overwritten_zero_load_is_not_mistaken_for_idempotency(self):
        source = self.power.read_text().replace(
            '    :goto_1c\n',
            '    const/16 v16, 0x0\n    move/from16 v16, v3\n    :goto_1c\n')
        self.power.write_text(source)
        self.assertTrue(MOD.patch(self.root))
        self.assertIn('    :goto_1c\n    const/16 v16, 0x0\n\n    sput-boolean v16, ', self.power.read_text())
        self.assertFalse(MOD.patch(self.root))

    def test_zero_load_before_other_instruction_is_not_idempotent(self):
        source = self.power.read_text().replace(
            '    :goto_1c\n', '    :goto_1c\n    const/16 v16, 0x0\n    nop\n')
        self.power.write_text(source)
        self.assertTrue(MOD.patch(self.root))
        self.assertIn('    nop\n    const/16 v16, 0x0\n\n    sput-boolean', self.power.read_text())

    def test_immediate_zero_load_with_comments_is_idempotent(self):
        source = self.power.read_text().replace(
            '    :goto_1c\n', '    :goto_1c\n    const/16 v16, 0x0\n    # native S10 HAL\n\n')
        self.power.write_text(source)
        self.assertFalse(MOD.patch(self.root))
        self.assertEqual(self.power.read_text(), source)



if __name__ == '__main__':
    unittest.main()
