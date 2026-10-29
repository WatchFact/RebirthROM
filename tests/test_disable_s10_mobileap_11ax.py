"""Regression tests for guarded Android 16 S10 MobileAP 11ax adaptation."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/disable_s10_mobileap_11ax.py'
spec = importlib.util.spec_from_file_location('s10_mobileap_11ax', HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CONFIG = '''.class public Lcom/samsung/android/server/wifi/ap/SemSoftApConfiguration;
.super Ljava/lang/Object;
.method public static showSecProductFeature()Ljava/lang/String;
    .locals 4
    const-string v1, "SPF_11ax=true\\nSPF_6G=true\\n"
    return-object v1
.end method
'''
CHIP = '''.class public Lcom/samsung/android/server/wifi/ap/SemWifiApChipInfo;
.super Ljava/lang/Object;
.method public supportThisSoftApFeature(I)Z
    .locals 3
    const/4 v0, 0x1
    if-eq p1, v0, :cond_2
    const/4 v1, 0x2
    if-eq p1, v1, :cond_2
    const/4 v1, 0x3
    const/4 v2, 0x0
    if-eq p1, v1, :cond_0
    return v2
    :cond_0
    invoke-virtual {p0}, Lcom/samsung/android/server/wifi/ap/SemWifiApChipInfo;->isSupportedSoftApPowerSave()Z
    move-result p1
    if-nez p1, :cond_2
    :cond_1
    return v2
    :cond_2
    :goto_0
    return v0
.end method
'''
SUPPORT = '''.class public Lcom/samsung/android/server/wifi/ap/SemWifiApChipInfo$SemWifiApChipSupportInfo;
.super Ljava/lang/Object;
.field public final featureArray:[B
.method public final isSupportedSoftAp11ax()Z
    .locals 5
    iget-object v0, p0, Lcom/samsung/android/server/wifi/ap/SemWifiApChipInfo$SemWifiApChipSupportInfo;->featureArray:[B
    and-int/2addr p0, v4
    const-string v3, "isSupportedSoftAp11ax : %s"
    return v4
.end method
'''


class S10MobileAp11axTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = []
        for suffix, contents in zip(module.CLASSES, (CONFIG, CHIP, SUPPORT)):
            path = self.root / 'smali' / suffix
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding='utf-8')
            self.paths.append(path)

    def test_disables_only_hotspot_11ax_capabilities(self):
        module.run(self.root)
        config, chip, support = [p.read_text() for p in self.paths]
        self.assertIn('SPF_11ax=false\\nSPF_6G=true\\n', config)
        self.assertIn('if-eq p1, v0, :cond_1', chip)
        self.assertIn('if-eq p1, v1, :cond_2', chip)
        self.assertIn('isSupportedSoftApPowerSave()Z', chip)
        self.assertIn('.locals 1\n\n    const/4 v0, 0x0\n\n    return v0', support)
        self.assertNotIn('SPF_11ax=true', config)

    def test_dry_run_never_writes(self):
        before = [p.read_bytes() for p in self.paths]
        module.run(self.root, check=True)
        self.assertEqual(before, [p.read_bytes() for p in self.paths])

    def test_missing_class_rejected_before_writes(self):
        self.paths[2].unlink()
        with self.assertRaisesRegex(ValueError, 'expected one donor class'):
            module.run(self.root)
        self.assertEqual(self.paths[0].read_text(), CONFIG)

    def test_duplicate_class_rejected(self):
        duplicate = self.root / 'smali_classes2' / module.CLASSES[2]
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text(SUPPORT)
        with self.assertRaisesRegex(ValueError, 'found 2'):
            module.run(self.root)

    def test_unexpected_hotspot_dump_rejected(self):
        self.paths[0].write_text(CONFIG.replace('SPF_11ax=true', 'SPF_11ax=unknown'))
        with self.assertRaisesRegex(ValueError, 'unexpected Android 16 hotspot feature dump'):
            module.run(self.root)

    def test_changed_feature_dispatch_rejected_without_partial_write(self):
        self.paths[1].write_text(CHIP.replace('if-eq p1, v0, :cond_2', 'if-ne p1, v0, :cond_2'))
        with self.assertRaisesRegex(ValueError, 'unexpected Android 16 hotspot capability dispatch'):
            module.run(self.root)
        self.assertEqual(self.paths[0].read_text(), CONFIG)

    def test_changed_chip_probe_rejected_without_partial_write(self):
        self.paths[2].write_text(SUPPORT.replace('and-int/2addr p0, v4', 'and-int/2addr p0, v3'))
        with self.assertRaisesRegex(ValueError, 'unexpected Android 16 chip 11ax probe'):
            module.run(self.root)
        self.assertEqual(self.paths[0].read_text(), CONFIG)

    def test_wrong_class_descriptor_rejected(self):
        self.paths[0].write_text(CONFIG.replace('SemSoftApConfiguration;', 'OtherConfiguration;'))
        with self.assertRaisesRegex(ValueError, 'malformed or incompatible class'):
            module.run(self.root)

    def test_duplicate_method_rejected(self):
        self.paths[0].write_text(CONFIG + CONFIG[CONFIG.index('.method'):])
        with self.assertRaisesRegex(ValueError, 'expected one method'):
            module.run(self.root)

    def test_repeat_application_rejected_not_corrupted(self):
        module.run(self.root)
        after = [p.read_bytes() for p in self.paths]
        with self.assertRaises(ValueError):
            module.run(self.root)
        self.assertEqual(after, [p.read_bytes() for p in self.paths])

    def test_missing_decoded_jar_rejected(self):
        with self.assertRaisesRegex(ValueError, 'decoded semwifi-service.jar directory missing'):
            module.run(self.root / 'missing')


if __name__ == '__main__':
    unittest.main()
