"""Fail-closed regression tests for the Android 16 S10 face HIDL 2.0 rebase."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts/backport_s10_face_hidl.py"
spec = importlib.util.spec_from_file_location("backport_s10_face_hidl", MODULE)
face = importlib.util.module_from_spec(spec)
spec.loader.exec_module(face)


def interface_fixture(desc):
    return f'''.method public final interfaceChain()Ljava/util/ArrayList;
    .locals 4
    const-string/jumbo v2, "vendor.samsung.hardware.biometrics.face@3.0::{desc}"

    const-string/jumbo v3, "vendor.samsung.hardware.biometrics.face@2.0::{desc}"

    filled-new-array {{v2, v3, v0, v1}}, [Ljava/lang/String;
    return-object v0
.end method
.method public final getHashChain()Ljava/util/ArrayList;
    .locals 4
    filled-new-array {{v1, v2, v3, v0}}, [[B
    return-object v0
.end method
'''


class S10FaceRebaseTests(unittest.TestCase):
    def test_filter_preserves_v2_proxy_and_unrelated_hunks(self):
        files = list(sorted(face.FILTER_FILES)) + [
            "smali/com/android/server/biometrics/sensors/face/aidl/SemFaceServiceExImpl.smali",
            "smali_classes2/vendor/samsung/hardware/biometrics/face/V2_0/ISehBiometricsFace$Proxy.smali",
        ]
        patch = "From 1234\nSubject: legacy face\n\n" + "".join(
            f"diff --git a/{p} b/{p}\n--- a/{p}\n+++ b/{p}\n@@ -1 +1 @@\n-old\n+new\n"
            for p in files
        )
        output = face.filter_patch(patch)
        self.assertIn("From 1234", output)
        self.assertEqual(output.count("diff --git "), 2)
        self.assertIn("SemFaceServiceExImpl.smali", output)
        self.assertIn("ISehBiometricsFace$Proxy.smali", output)
        for p in face.FILTER_FILES:
            self.assertNotIn(f"diff --git a/{p}", output)
        with self.assertRaises(face.DonorMismatch):
            face.filter_patch(patch.replace("diff --git a/" + files[0], "diff --git a/other", 1))

    def test_real_shared_patch_has_exact_expected_classes(self):
        root = Path(__file__).resolve().parents[1]
        patch = root / "unica/patches/legacy/face/services.jar/0001-Fallback-to-Face-HIDL-2.0.patch"
        filtered = face.filter_patch(patch.read_text(encoding="utf-8"))
        self.assertIn("ISehBiometricsFace$Proxy.smali", filtered)
        self.assertIn("HidlToAidlSessionAdapter.smali", filtered)
        self.assertNotIn("diff --git a/" + face.CLASS_PATHS["TestHal"], filtered)
        shell = (root / "unica/patches/legacy/customize.sh").read_text(encoding="utf-8")
        self.assertIn('if [[ "$TARGET_PLATFORM" == "exynos9820" ]]; then', shell)
        self.assertIn('backport_s10_face_hidl.py" adapt', shell)
        self.assertIn('SemFaceServiceExImpl\$\$ExternalSyntheticLambda6.smali" "remove"', shell)
        self.assertLess(
            shell.index('if [[ "$TARGET_PLATFORM" == "exynos9820" ]]; then', shell.index("# Support legacy Face HAL")),
            shell.index('SemFaceServiceExImpl\$\$ExternalSyntheticLambda6.smali" "remove"'),
        )

    def test_auth_uses_existing_v2_path(self):
        source = '''.method public final semDoAuthenticate()V
    .locals 17
    if-eqz v9, :cond_0
    :cond_0
    iget-boolean v9, v2, Lcom/android/server/biometrics/sensors/face/aidl/SemFaceServiceExImpl;->mIsAuthenticationExtOperation:Z
    const-string v10, "HidlToAidlSessionAdapter"
    if-eqz v9, :cond_2
    check-cast v11, Lvendor/samsung/hardware/biometrics/face/V3_0/ISehBiometricsFace;
    invoke-interface/range {v11 .. v16}, Lvendor/samsung/hardware/biometrics/face/V3_0/ISehBiometricsFace;->sehAuthenticateForIssuance(JILjava/util/ArrayList;Z)I
    :cond_2
    invoke-virtual {v1}, Lcom/android/server/biometrics/sensors/face/aidl/AidlSession;->getSession()Landroid/hardware/biometrics/face/ISession;
    invoke-interface {v11, v12, v13, v7, v9}, Lvendor/samsung/hardware/biometrics/face/V2_0/ISehBiometricsFace;->sehAuthenticate(JILjava/util/ArrayList;)I
    return-void
.end method
'''
        adapted = face.adapt_auth(source)
        self.assertNotIn("sehAuthenticateForIssuance", adapted)
        self.assertIn("->sehAuthenticate(JILjava/util/ArrayList;)I", adapted)
        self.assertIn('const-string v10, "HidlToAidlSessionAdapter"', adapted)
        with self.assertRaises(face.DonorMismatch):
            face.adapt_auth(source.replace("mIsAuthenticationExtOperation", "mChangedField"))

    def test_callback_removes_v3_transaction_and_hash(self):
        source = interface_fixture("ISehBiometricsFaceClientCallback") + '''
.implements Lvendor/samsung/hardware/biometrics/face/V3_0/ISehBiometricsFaceClientCallback;
.method public final onTransact(ILandroid/os/HwParcel;Landroid/os/HwParcel;I)V
    .locals 3
    packed-switch p1, :pswitch_data_0
    :pswitch_0
    const-string v0, "sehOnAuthenticatedFromMemory"
    return-void
    :pswitch_1
    return-void
    :pswitch_data_0
    .packed-switch 0x1
        :pswitch_1
        :pswitch_0
    .end packed-switch
.end method
'''
        output = face.adapt_callback(source)
        self.assertNotIn("sehOnAuthenticatedFromMemory", output)
        self.assertNotIn("V3_0", output)
        self.assertIn(".implements Lvendor/samsung/hardware/biometrics/face/V2_0/", output)
        self.assertIn("filled-new-array {v3, v0, v1}", output)
        self.assertIn("filled-new-array {v2, v3, v0}", output)
        self.assertEqual(output.count("        :pswitch_1"), 1)
        self.assertNotIn("        :pswitch_0", output)

    def test_testhal_removes_v3_only_transactions_and_methods(self):
        source = interface_fixture("ISehBiometricsFace") + '''
.implements Lvendor/samsung/hardware/biometrics/face/V3_0/ISehBiometricsFace;
.method public final onTransact(ILandroid/os/HwParcel;Landroid/os/HwParcel;I)V
    .locals 10
    packed-switch p1, :pswitch_data_0
    :pswitch_0
    const-string v0, "sehAuthenticateForIssuance"
    return-void
    :pswitch_1
    const-string v0, "sehSetCallbackEx"
    return-void
    :pswitch_2
    return-void
    :pswitch_data_0
    .packed-switch 0x1
        :pswitch_2
        :pswitch_1
        :pswitch_0
    .end packed-switch
.end method
.method public final sehAuthenticateForIssuance(JILjava/util/ArrayList;Z)I
    .locals 0
    return p0
.end method
.method public sehSetCallbackEx(Lvendor/samsung/hardware/biometrics/face/V3_0/ISehBiometricsFaceClientCallback;)Landroid/hardware/biometrics/face/V1_0/OptionalUint64;
    .locals 0
    return-object p0
.end method
'''
        output = face.adapt_test_hal(source)
        self.assertNotIn("sehAuthenticateForIssuance", output)
        self.assertNotIn("sehSetCallbackEx", output)
        self.assertNotIn("V3_0", output)
        self.assertIn("filled-new-array {v3, v0, v1}", output)
        self.assertEqual(output.count("        :pswitch_2"), 1)
        self.assertNotIn("        :pswitch_0", output)
        self.assertNotIn("        :pswitch_1", output)

    def test_labels_fail_closed(self):
        with self.assertRaises(face.DonorMismatch):
            face.validate_labels("    :cond_0\n    :cond_0\n", "x")
        with self.assertRaises(face.DonorMismatch):
            face.validate_labels("    goto :cond_3\n    :cond_0\n", "x")
        face.validate_labels('    goto :cond_0\n    :cond_0\n    const-string v0, "foo::IBar"\n', "x")

    def test_missing_donor_is_atomic(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for path in face.CLASS_PATHS.values():
                p = root / path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("unchanged")
            with self.assertRaises(face.DonorMismatch):
                face.adapt_dir(root)
            for path in face.CLASS_PATHS.values():
                self.assertEqual((root / path).read_text(), "unchanged")


if __name__ == "__main__":
    unittest.main()
