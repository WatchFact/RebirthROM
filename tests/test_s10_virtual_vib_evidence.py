"""Regression checks for read-only virtual-vibration donor evidence collection."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/collect_s10_virtual_vib_evidence.py'
spec = importlib.util.spec_from_file_location('vib_evidence', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

PATCH = ('diff --git a/smali_classes2/com/android/server/vibrator/Test.smali '
         'b/smali_classes2/com/android/server/vibrator/Test.smali\n')


class EvidenceTests(unittest.TestCase):
    def test_patch_inventory_and_reject_mismatched_path(self):
        self.assertEqual(module.patch_classes(PATCH), ['smali_classes2/com/android/server/vibrator/Test.smali'])
        with self.assertRaises(ValueError):
            module.patch_classes(PATCH.replace('b/smali_classes2', 'b/smali_classes3'))

    def test_missing_class_reported_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = module.capture(root, PATCH)
            self.assertIn('Donor class matches: 0', result)
            self.assertEqual(list(root.iterdir()), [])

    def test_relocated_class_captured_completely(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file = root / 'smali_classes5/com/android/server/vibrator/Test.smali'
            file.parent.mkdir(parents=True)
            content = '.class public LTest;\n.method public final onExternalVibrationStart()V\n    return-void\n.end method\n'
            file.write_text(content)
            result = module.capture(root, PATCH)
            self.assertIn('smali_classes5/com/android/server/vibrator/Test.smali', result)
            self.assertIn('Complete class (bounded)', result)
            self.assertIn('onExternalVibrationStart', result)
            self.assertEqual(file.read_text(), content)

    def test_duplicate_class_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for smali in ('smali', 'smali_classes3'):
                file = root / smali / 'com/android/server/vibrator/Test.smali'
                file.parent.mkdir(parents=True)
                file.write_text('.class public LTest;\n')
            result = module.capture(root, PATCH)
            self.assertIn('Donor class matches: 2', result)
            self.assertIn('missing or ambiguous class', result)

    def test_large_class_selects_relevant_method(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file = root / 'smali/com/android/server/vibrator/Test.smali'
            file.parent.mkdir(parents=True)
            filler = '# filler\n' * (module.MAX_FULL_CLASS_LINES + 1)
            file.write_text('.class public LTest;\n' + filler + '.method public onExternalVibrationStart()V\n    return-void\n.end method\n')
            result = module.capture(root, PATCH)
            self.assertIn('Large class', result)
            self.assertIn('onExternalVibrationStart', result)

    def test_unpatched_helper_dependency_is_captured_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            helper = root / 'smali_classes3/com/android/server/vibrator/VirtualVibSoundHelper.smali'
            helper.parent.mkdir(parents=True)
            original = ('.class public Lcom/android/server/vibrator/VirtualVibSoundHelper;\n'
                        '.method public stopVirtualSound(Ljava/lang/String;)V\n'
                        '    return-void\n.end method\n')
            helper.write_text(original)
            result = module.capture(root, PATCH)
            self.assertIn('VirtualVibSoundHelper.smali', result)
            self.assertIn('smali_classes3/com/android/server/vibrator/VirtualVibSoundHelper.smali', result)
            self.assertIn('stopVirtualSound', result)
            self.assertEqual(helper.read_text(), original)

    def test_large_donor_capture_budget_includes_multiple_methods(self):
        self.assertGreaterEqual(module.MAX_METHODS, 18)
        self.assertGreaterEqual(module.MAX_TOTAL_LINES, 50000)

    def test_malformed_method_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file = root / 'smali/com/android/server/vibrator/Test.smali'
            file.parent.mkdir(parents=True)
            file.write_text('.method public broken()V\n')
            with self.assertRaisesRegex(ValueError, 'unterminated'):
                module.capture(root, PATCH)


if __name__ == '__main__':
    unittest.main()
