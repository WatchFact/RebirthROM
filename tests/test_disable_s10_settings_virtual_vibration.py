#!/usr/bin/env python3
"""Synthetic regression tests; no proprietary donor smali is committed."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/disable_s10_settings_virtual_vibration.py'
spec = importlib.util.spec_from_file_location('s10_settings_vib', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SettingsVibTests(unittest.TestCase):
    def test_search_donor_without_feature_is_unchanged(self):
        self.assertEqual(mod.adapt('.class public Lx;\n', 'search'), '.class public Lx;\n')

    def test_search_donor_with_feature_is_rejected(self):
        with self.assertRaises(ValueError):
            mod.adapt('"vibration_sound_enabled"', 'search')

    def test_reset_removes_only_unsupported_write(self):
        src = ('other_setting\n    const-string/jumbo p1, "vibration_sound_enabled"\n\n'
               '    invoke-static {p0, p1, v2}, Landroid/provider/Settings$System;->putInt(Landroid/content/ContentResolver;Ljava/lang/String;I)Z\n\n'
               'return-void\n')
        self.assertEqual(mod.adapt(src, 'reset'), 'other_setting\nreturn-void\n')

    def test_reset_unknown_register_rejected(self):
        with self.assertRaises(ValueError):
            mod.adapt('    const-string/jumbo v0, "vibration_sound_enabled"\n', 'reset')

    def test_controller_rejects_unknown_availability(self):
        with self.assertRaises(ValueError):
            mod.adapt('.method public getAvailabilityStatus()I\n    .locals 0\n    const/4 p0, 0x1\n    return p0\n.end method\n', 'controller')

    def test_backup_disables_only_restore_arm(self):
        src = ('.method public restore()V\n    :pswitch_1f\n    const-string v0, "other"\n    return-object p0\n'
               '    :pswitch_20\n    return-object p0\n.end method\n'
               '.method public restoreTwo()V\n    :pswitch_1f\n'
               '    const-string/jumbo v0, "vibration_sound_enabled"\n'
               '    invoke-static {v3, v0, v2}, Landroid/provider/Settings$System;->putInt(Landroid/content/ContentResolver;Ljava/lang/String;I)Z\n'
               '    return-object p0\n\n    :pswitch_20\n    return-object p0\n.end method\n')
        result = mod.adapt(src, 'backup')
        self.assertIn('const-string v0, "other"', result)
        self.assertNotIn('"vibration_sound_enabled"', result)
        self.assertIn('    :pswitch_1f\n    return-object p0\n', result)

    def test_backup_missing_restore_is_rejected(self):
        with self.assertRaises(ValueError):
            mod.adapt('    :pswitch_1f\n    return-object p0\n    :pswitch_20\n', 'backup')

    def test_missing_class_does_not_modify_other_classes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'smali' / 'com/samsung/android/settings/asbase/audio/SoundSettings$3.smali'
            path.parent.mkdir(parents=True)
            original = '.class public Lx;\n'
            path.write_text(original)
            with self.assertRaises(ValueError):
                mod.run(root)
            self.assertEqual(path.read_text(), original)


if __name__ == '__main__':
    unittest.main()
