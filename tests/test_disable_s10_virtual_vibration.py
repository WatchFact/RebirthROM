#!/usr/bin/env python3
"""Synthetic regression tests; no proprietary donor classes are redistributed."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/disable_s10_virtual_vibration.py'
spec = importlib.util.spec_from_file_location('disable_s10_virtual_vibration', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ORIGINAL = '''.method public final bootCompleteReady()V
    .locals 1

    new-instance v0, Lcom/android/server/vibrator/VirtualVibSoundHelper;

    iput-object v0, p0, Lcom/android/server/vibrator/VibratorManagerService;->mVirtualVibSoundHelper:Lcom/android/server/vibrator/VirtualVibSoundHelper;

    invoke-virtual {p0}, Lcom/android/server/vibrator/VibratorManagerService;->registerFoldStateListener()V

    return-void
.end method'''
READ = ('    iget-object v0, p0, ' + mod.FIELD + '\n\n'
        '    if-eqz v0, :cond_0\n\n'
        '    invoke-virtual {v0}, Ljava/lang/Object;->toString()Ljava/lang/String;\n')


class S10VirtualVibrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manager = self.root / 'smali_classes2/com/android/server/vibrator/VibratorManagerService.smali'
        self.reader = self.root / 'smali_classes2/com/android/server/vibrator/Callback.smali'
        self.manager.parent.mkdir(parents=True)
        self.manager.write_text('.class public Lcom/android/server/vibrator/VibratorManagerService;\n'
                                + ORIGINAL + '\n')
        self.reader.write_text('.method public run()V\n    .locals 1\n'
                               + READ + '    :cond_0\n    return-void\n.end method\n')
        self.digest = hashlib.sha256(ORIGINAL.encode()).hexdigest()
        self.expected = patch.object(mod, 'EXPECTED_METHOD_SHA256', self.digest)
        self.expected.start()
        self.addCleanup(self.expected.stop)

    def test_rebase_preserves_hardware_listener(self):
        self.assertTrue(mod.disable(self.root))
        content = self.manager.read_text()
        self.assertIn(mod.PATCHED_METHOD, content)
        self.assertIn('registerFoldStateListener()V', content)
        self.assertNotIn('new-instance v0', content)
        self.assertIn('if-eqz v0', self.reader.read_text())

    def test_repeat_is_idempotent(self):
        self.assertTrue(mod.disable(self.root))
        self.assertFalse(mod.disable(self.root))

    def test_unknown_donor_rejected_without_writes(self):
        before = self.manager.read_text().replace('    .locals 1', '    .locals 2')
        self.manager.write_text(before)
        with self.assertRaisesRegex(ValueError, 'unknown Android 16'):
            mod.disable(self.root)
        self.assertEqual(self.manager.read_text(), before)

    def test_unguarded_reference_rejected_without_writes(self):
        self.reader.write_text(self.reader.read_text().replace('if-eqz v0, :cond_0', 'const/4 v0, 0x0'))
        before = self.manager.read_text()
        with self.assertRaisesRegex(ValueError, 'unguarded'):
            mod.disable(self.root)
        self.assertEqual(self.manager.read_text(), before)

    def test_wrong_register_guard_rejected(self):
        self.reader.write_text(self.reader.read_text().replace('if-eqz v0, :cond_0', 'if-eqz v1, :cond_0'))
        with self.assertRaisesRegex(ValueError, 'unguarded'):
            mod.disable(self.root)

    def test_second_helper_writer_rejected(self):
        self.reader.write_text(self.reader.read_text() + '\n    iput-object v0, p0, ' + mod.FIELD + '\n')
        with self.assertRaisesRegex(ValueError, 'unexpected virtual-vibration helper assignment'):
            mod.disable(self.root)

    def test_missing_manager_rejected(self):
        self.manager.unlink()
        with self.assertRaisesRegex(ValueError, 'expected one regular'):
            mod.disable(self.root)

    def test_duplicate_manager_rejected(self):
        other = self.root / 'smali/com/android/server/vibrator/VibratorManagerService.smali'
        other.parent.mkdir(parents=True)
        other.write_text(self.manager.read_text())
        with self.assertRaisesRegex(ValueError, 'expected one regular'):
            mod.disable(self.root)

    def test_symlink_manager_rejected(self):
        original = self.root / 'original.smali'
        original.write_text(self.manager.read_text())
        self.manager.unlink()
        self.manager.symlink_to(original)
        with self.assertRaisesRegex(ValueError, 'expected one regular'):
            mod.disable(self.root)


if __name__ == '__main__':
    unittest.main()
