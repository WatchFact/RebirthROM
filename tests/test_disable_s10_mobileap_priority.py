"""Synthetic regression tests for the Android 16 S10 hotspot-priority guard."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('s10_priority', ROOT / 'scripts/disable_s10_mobileap_priority.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

PROXY = '''.class public Lcom/samsung/android/server/wifi/SemWifiManagerProxy;
.super Ljava/lang/Object;
.method public isWifiApSmartPrioritySupported()Z
    .locals 0

    const/4 p0, 0x1

    return p0
.end method
'''
RESET = '''.class public Lcom/samsung/android/server/wifi/ap/SemSettingsSoftResetHandler;
.super Ljava/lang/Object;
.method public resetHotspotSettings()V
    .locals 6
    const-string v2, "wifi_ap_smart_priority_enable"
    const/4 v3, 0x0
    invoke-static {v0, v2, v3}, Landroid/provider/Settings$Secure;->putInt(Landroid/content/ContentResolver;Ljava/lang/String;I)Z
    return-void
.end method
'''
RECEIVER = '''.class public Lcom/samsung/android/server/wifi/ap/SemWifiApBroadcastReceiver;
.super Ljava/lang/Object;
.method public final addTheSmartHotspotInfo(Lorg/json/JSONObject;)V
    .locals 6
    invoke-virtual {p0}, Lcom/samsung/android/server/wifi/ap/SemWifiApBroadcastReceiver;->getTrafficPriorityStatus()Ljava/lang/String;
    move-result-object v1
    const-string v0, "mh_tp"
    return-void
.end method
.method public final getTrafficPriorityStatus()Ljava/lang/String;
    .locals 2
    invoke-virtual {p0}, Lcom/samsung/android/server/wifi/SemWifiInjector;->getSemWifiApTrafficPriority()Lcom/samsung/android/server/wifi/ap/smartprio/SemWifiApTrafficPriority;
    invoke-virtual {p0}, Lcom/samsung/android/server/wifi/ap/smartprio/SemWifiApTrafficPriority;->getmIsPriorityFeatureEnableDuringSession()Z
    invoke-virtual {p0}, Lcom/samsung/android/server/wifi/ap/smartprio/SemWifiApTrafficPriority;->getNRTTrafficEnable()Z
    invoke-virtual {p0}, Lcom/samsung/android/server/wifi/ap/smartprio/SemWifiApTrafficPriority;->getRTTrafficEnable()Z
    const-string p0, "tp_rt"
    const-string p0, "tp_nrt"
    const-string p0, "tp_on_below_cutoff"
    const-string p0, "tp_off"
    const-string v0, "handleWifiApState: "
    return-object p0
.end method
'''


class PriorityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.paths = []
        for suffix, data in zip((module.PROXY, module.RESET, module.RECEIVER),
                                (PROXY, RESET, RECEIVER)):
            path = self.root / 'smali' / suffix
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
            self.paths.append(path)

    def snapshot(self):
        return [p.read_bytes() for p in self.paths]

    def test_adapts_only_unsupported_feature(self):
        module.run(self.root)
        p, r, b = [x.read_text() for x in self.paths]
        self.assertIn('const/4 p0, 0x0', p)
        self.assertIn('"wifi_ap_smart_priority_enable"', r)
        self.assertIn('const-string p0, "not_support"', b)
        self.assertIn('"mh_tp"', b)
        self.assertNotIn('getSemWifiApTrafficPriority()', b)

    def test_dry_run(self):
        before = self.snapshot()
        module.run(self.root, check=True)
        self.assertEqual(before, self.snapshot())

    def test_missing_class(self):
        self.paths[1].unlink()
        with self.assertRaisesRegex(ValueError, 'expected one donor class'):
            module.run(self.root)

    def test_duplicate_class(self):
        path = self.root / 'smali_classes2' / module.PROXY
        path.parent.mkdir(parents=True)
        path.write_text(PROXY)
        with self.assertRaisesRegex(ValueError, 'found 2'):
            module.run(self.root)

    def test_changed_probe(self):
        self.paths[0].write_text(PROXY.replace('const/4 p0, 0x1', 'const/4 p0, 0x2'))
        with self.assertRaisesRegex(ValueError, 'unexpected priority support probe'):
            module.run(self.root)

    def test_changed_reset_rejects_without_partial_write(self):
        self.paths[1].write_text(RESET.replace('wifi_ap_smart_priority_enable', 'other_setting'))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'no longer clears priority setting'):
            module.run(self.root)
        self.assertEqual(before, self.snapshot())

    def test_changed_status_rejects_without_partial_write(self):
        self.paths[2].write_text(RECEIVER.replace('getRTTrafficEnable', 'getRTTrafficOther'))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'unexpected traffic-priority status method'):
            module.run(self.root)
        self.assertEqual(before, self.snapshot())

    def test_changed_telemetry(self):
        self.paths[2].write_text(RECEIVER.replace('"mh_tp"', '"other"'))
        with self.assertRaisesRegex(ValueError, 'unexpected hotspot telemetry wiring'):
            module.run(self.root)

    def test_duplicate_method(self):
        self.paths[0].write_text(PROXY + PROXY[PROXY.index('.method'):])
        with self.assertRaisesRegex(ValueError, 'expected one method'):
            module.run(self.root)

    def test_repeat_rejected(self):
        module.run(self.root)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            module.run(self.root)
        self.assertEqual(before, self.snapshot())

    def test_missing_decoded_jar(self):
        with self.assertRaisesRegex(ValueError, 'decoded semwifi-service.jar directory missing'):
            module.run(self.root / 'missing')


if __name__ == '__main__':
    unittest.main()
