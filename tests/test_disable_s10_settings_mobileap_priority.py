"""Synthetic regressions for the S10+ Android 16 hotspot-priority guard."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'guard', Path(__file__).resolve().parents[1] / 'scripts/disable_s10_settings_mobileap_priority.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

INDEX = '''.class public Lcom/samsung/android/settings/wifi/mobileap/WifiApSettings$1;
.super Ljava/lang/Object;
.method public final getRawDataToIndex(Landroid/content/Context;)Ljava/util/List;
    .locals 4
    const-string v0, "guest_mode_switch_preference"
    if-eqz v0, :cond_2
    return-object p0
    :cond_2
    new-instance v1, Lcom/android/settingslib/search/SearchIndexableRaw;
    invoke-direct {v1, p1}, Landroid/provider/SearchIndexableData;-><init>(Landroid/content/Context;)V
    const-string v1, "smart_priority_switch_preference"
    iput-object v1, p0, Lcom/android/settingslib/search/SearchIndexableRaw;->title:Ljava/lang/String;
    return-object p0
.end method
'''
CTRL = '''.class public Lcom/samsung/android/settings/wifi/mobileap/smartpriority/WifiApSmartPrioritySwitchController;
.super Ljava/lang/Object;
.method public getAvailabilityStatus()I
    .locals 1
    invoke-static {p0}, Lcom/samsung/android/settings/wifi/mobileap/utils/WifiApFeatureUtils;->isMobileDataUsageSupported(Landroid/content/Context;)Z
    return p0
.end method
.method public isChecked()Z
    .locals 1
    const-string v0, "wifi_ap_smart_priority_enable"
    return p0
.end method
.method public setChecked(Z)Z
    .locals 1
    invoke-static {p0, p1}, Lcom/samsung/android/settings/wifi/mobileap/utils/WifiApFrameworkUtils;->setPrioritizeRealTimeTrafficDB(Landroid/content/Context;Z)V
    return p0
.end method
'''
UTILS = '''.class public Lcom/samsung/android/settings/wifi/mobileap/utils/WifiApFrameworkUtils;
.super Ljava/lang/Object;
.method public static isPrioritizeRealTimeTrafficOn(Landroid/content/Context;)Z
    .locals 1
    const-string v0, "wifi_ap_smart_priority_enable"
    return p0
.end method
.method public static setPrioritizeRealTimeTrafficDB(Landroid/content/Context;Z)V
    .locals 1
    const-string v0, "wifi_ap_smart_priority_enable"
    return-void
.end method
'''


class GuardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        old = guard.DONOR
        self.addCleanup(setattr, guard, 'DONOR', old)
        fixtures = {guard.INDEX: INDEX, guard.CONTROLLER: CTRL, guard.UTILS: UTILS}
        self.paths = {}
        for suffix in guard.DONOR:
            content = fixtures.get(suffix, '.class public L' + suffix.removesuffix('.smali') +
                                   ';\n.super Ljava/lang/Object;\n')
            p = self.root / 'smali' / suffix
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            self.paths[suffix] = p
        guard.DONOR = {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in self.paths.items()}

    def snapshot(self):
        return {k: p.read_bytes() for k, p in self.paths.items()}

    def test_adapt_preserves_other_classes(self):
        before = self.snapshot()
        guard.run(self.root)
        self.assertNotIn('smart_priority_switch_preference', self.paths[guard.INDEX].read_text())
        self.assertIn('guest_mode_switch_preference', self.paths[guard.INDEX].read_text())
        self.assertIn('const/4 p0, 0x3', self.paths[guard.CONTROLLER].read_text())
        self.assertNotIn('wifi_ap_smart_priority_enable', self.paths[guard.UTILS].read_text())
        for suffix in before:
            if suffix not in (guard.INDEX, guard.CONTROLLER, guard.UTILS):
                self.assertEqual(before[suffix], self.paths[suffix].read_bytes())

    def test_check_no_writes(self):
        before = self.snapshot()
        guard.run(self.root, check=True)
        self.assertEqual(before, self.snapshot())

    def test_missing_class(self):
        self.paths[guard.INDEX].unlink()
        with self.assertRaisesRegex(ValueError, 'expected one donor class'):
            guard.run(self.root)

    def test_duplicate_class(self):
        p = self.root / 'smali_classes2' / guard.UTILS
        p.parent.mkdir(parents=True)
        p.write_bytes(self.paths[guard.UTILS].read_bytes())
        with self.assertRaisesRegex(ValueError, 'found 2'):
            guard.run(self.root)

    def test_digest_mismatch_atomic(self):
        p = self.paths[guard.CONTROLLER]
        p.write_text(p.read_text().replace('isMobileDataUsageSupported', 'changed'))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'unverified donor digest'):
            guard.run(self.root)
        self.assertEqual(before, self.snapshot())

    def test_changed_method_atomic(self):
        p = self.paths[guard.CONTROLLER]
        p.write_text(p.read_text().replace('isMobileDataUsageSupported', 'changed'))
        guard.DONOR[guard.CONTROLLER] = hashlib.sha256(p.read_bytes()).hexdigest()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'donor wiring changed'):
            guard.run(self.root)
        self.assertEqual(before, self.snapshot())

    def test_changed_search_atomic(self):
        p = self.paths[guard.INDEX]
        p.write_text(p.read_text().replace('smart_priority_switch_preference', 'changed'))
        guard.DONOR[guard.INDEX] = hashlib.sha256(p.read_bytes()).hexdigest()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'unexpected priority search layout'):
            guard.run(self.root)
        self.assertEqual(before, self.snapshot())

    def test_repeat_fails_closed(self):
        guard.run(self.root)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'unverified donor digest'):
            guard.run(self.root)
        self.assertEqual(before, self.snapshot())

    def test_missing_directory(self):
        with self.assertRaisesRegex(ValueError, 'decoded SecSettings directory missing'):
            guard.run(self.root / 'missing')


if __name__ == '__main__':
    unittest.main()
