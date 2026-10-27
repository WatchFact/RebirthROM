#!/usr/bin/env python3
"""Fail-closed Android 16 donor Face HIDL 2.0 rebase for Exynos9820.

The common patch remains unchanged for other platforms. Filter only its five
incompatible donor classes, then adapt their actual decoded Android 16 smali.
The donor's Lambda6 is already the face-removal callback: preserve it.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASE = "smali/com/android/server/biometrics/sensors/face"
AIDL = f"{BASE}/aidl"
HIDL = f"{BASE}/hidl"
CLASS_PATHS = {
    "AidlResponseHandler": f"{AIDL}/AidlResponseHandler.smali",
    "FaceAuthenticationClient": f"{AIDL}/FaceAuthenticationClient.smali",
    "HidlToAidlCallbackConverter": f"{HIDL}/HidlToAidlCallbackConverter.smali",
    "TestHal": f"{HIDL}/TestHal.smali",
}
FILTER_FILES = frozenset({
    *CLASS_PATHS.values(),
    f"{AIDL}/SemFaceServiceExImpl$$ExternalSyntheticLambda5.smali",
})


class DonorMismatch(RuntimeError):
    pass


def one(source: str, old: str, new: str, context: str) -> str:
    count = source.count(old)
    if count != 1:
        raise DonorMismatch(f"{context}: expected one anchor, found {count}: {old[:120]!r}")
    return source.replace(old, new, 1)


def validate_labels(method: str, name: str) -> None:
    definitions = re.findall(r"(?m)^    (:[a-zA-Z_][\w]*)[ \t]*$", method)
    if len(definitions) != len(set(definitions)):
        raise DonorMismatch(f"{name}: duplicate smali labels")
    references = set(re.findall(
        r"(?<![\w:]):(?:cond|goto|pswitch|sswitch|try_start|try_end|catch|array|pswitch_data|sswitch_data)_[\w]+",
        method,
    ))
    if not references.issubset(set(definitions)):
        raise DonorMismatch(f"{name}: undefined smali labels: {sorted(references-set(definitions))}")


def method_edit(source: str, name: str, callback) -> str:
    pattern = re.compile(
        r"(?m)^\.method [^\n]*" + re.escape(name) + r"\([^\n]*\n.*?^\.end method$",
        re.S,
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise DonorMismatch(f"expected exactly one method {name}, found {len(matches)}")
    old = matches[0].group()
    new = callback(old)
    validate_labels(new, name)
    return source[:matches[0].start()] + new + source[matches[0].end():]


def filter_patch(source: str) -> str:
    parts = re.split(r"(?=^diff --git )", source, flags=re.M)
    kept, removed = [], set()
    for part in parts:
        if not part.startswith("diff --git "):
            kept.append(part)
            continue
        match = re.match(r"diff --git a/(\S+) b/(\S+)", part)
        if not match or match.group(1) != match.group(2):
            raise DonorMismatch("unsupported patch header")
        path = match.group(1)
        if path in FILTER_FILES:
            if path in removed:
                raise DonorMismatch(f"duplicate patch entry: {path}")
            removed.add(path)
        else:
            kept.append(part)
    if removed != FILTER_FILES:
        raise DonorMismatch(f"face patch changed: missing {sorted(FILTER_FILES-removed)}")
    result = "".join(kept)
    if "diff --git " not in result:
        raise DonorMismatch("empty filtered patch")
    return result


def adapt_auth(source: str) -> str:
    def transform(method: str) -> str:
        # Remove only the unsupported V3 issuance branch. Fall through to
        # the donor's existing V2 sehAuthenticate and cancellation handling.
        start = (
            "    :cond_0\n"
            "    iget-boolean v9, v2, Lcom/android/server/biometrics/sensors/face/aidl/SemFaceServiceExImpl;->mIsAuthenticationExtOperation:Z\n"
        )
        end = (
            "    :cond_2\n"
            "    invoke-virtual {v1}, Lcom/android/server/biometrics/sensors/face/aidl/AidlSession;->getSession()Landroid/hardware/biometrics/face/ISession;"
        )
        if method.count(start) != 1 or method.count(end) != 1:
            raise DonorMismatch("FaceAuthenticationClient: V3 issuance branch anchors changed")
        a, b = method.index(start), method.index(end)
        removed = method[a:b]
        for anchor in (
            "sehAuthenticateForIssuance",
            "check-cast v11, Lvendor/samsung/hardware/biometrics/face/V3_0/",
            'const-string v10, "HidlToAidlSessionAdapter"',
        ):
            if anchor not in removed:
                raise DonorMismatch(f"FaceAuthenticationClient: missing anchor {anchor}")
        method = method[:a] + '    :cond_0\n    const-string v10, "HidlToAidlSessionAdapter"\n\n' + method[b:]
        if "V3_0/ISehBiometricsFace;" in method or "sehAuthenticateForIssuance" in method:
            raise DonorMismatch("FaceAuthenticationClient: V3 invocation remains")
        if method.count("->sehAuthenticate(JILjava/util/ArrayList;)I") != 1:
            raise DonorMismatch("FaceAuthenticationClient: missing V2 authentication path")
        return method
    return method_edit(source, "semDoAuthenticate", transform)


def adapt_interface(source: str, name: str, descriptor: str) -> str:
    def chain(method: str) -> str:
        v3 = f'    const-string/jumbo v2, "vendor.samsung.hardware.biometrics.face@3.0::{descriptor}"\n\n'
        method = one(method, v3, "", name + ".interfaceChain")
        return one(
            method,
            "    filled-new-array {v2, v3, v0, v1}, [Ljava/lang/String;",
            "    filled-new-array {v3, v0, v1}, [Ljava/lang/String;",
            name + ".interfaceChain",
        )
    source = method_edit(source, "interfaceChain", chain)
    def hashes(method: str) -> str:
        # array_0 hashes V3; arrays 1-3 hash V2, V1, and IBase.
        return one(
            method, "    filled-new-array {v1, v2, v3, v0}, [[B",
            "    filled-new-array {v2, v3, v0}, [[B", name + ".getHashChain",
        )
    source = method_edit(source, "getHashChain", hashes)
    source = source.replace("V3_0", "V2_0").replace("face@3.0", "face@2.0")
    if "V3_0" in source or "face@3.0" in source:
        raise DonorMismatch(f"{name}: obsolete V3 descriptor survives")
    return source


def adapt_callback(source: str) -> str:
    def transact(method: str) -> str:
        a, b = "    :pswitch_0\n", "    :pswitch_1\n"
        if (len(re.findall(r"(?m)^    :pswitch_0$", method)) != 1
                or len(re.findall(r"(?m)^    :pswitch_1$", method)) != 1):
            raise DonorMismatch("HidlToAidlCallbackConverter: transaction labels changed")
        i, j = method.index(a), method.index(b)
        if i >= j or "sehOnAuthenticatedFromMemory" not in method[i:j]:
            raise DonorMismatch("HidlToAidlCallbackConverter: V3 memory callback changed")
        method = method[:i] + method[j:]
        method = one(method, "        :pswitch_0\n", "", "HidlToAidlCallbackConverter switch")
        if "sehOnAuthenticatedFromMemory" in method:
            raise DonorMismatch("HidlToAidlCallbackConverter: V3 callback survives")
        return method
    source = method_edit(source, "onTransact", transact)
    return adapt_interface(source, "HidlToAidlCallbackConverter", "ISehBiometricsFaceClientCallback")


def remove_method(source: str, signature: str) -> str:
    pattern = re.compile(r"(?m)^\.method [^\n]*" + re.escape(signature) + r"\n.*?^\.end method\n", re.S)
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise DonorMismatch(f"expected one V3-only method {signature}, found {len(matches)}")
    return source[:matches[0].start()] + source[matches[0].end():]


def adapt_test_hal(source: str) -> str:
    def transact(method: str) -> str:
        a, b = "    :pswitch_0\n", "    :pswitch_2\n"
        if (len(re.findall(r"(?m)^    :pswitch_0$", method)) != 1
                or len(re.findall(r"(?m)^    :pswitch_2$", method)) != 1):
            raise DonorMismatch("TestHal: transaction labels changed")
        i, j = method.index(a), method.index(b)
        removed = method[i:j]
        if i >= j or "sehAuthenticateForIssuance" not in removed or "sehSetCallbackEx" not in removed:
            raise DonorMismatch("TestHal: V3-only transaction handlers changed")
        method = method[:i] + method[j:]
        method = one(method, "        :pswitch_0\n", "", "TestHal switch 0")
        return one(method, "        :pswitch_1\n", "", "TestHal switch 1")
    source = method_edit(source, "onTransact", transact)
    source = remove_method(source, "sehAuthenticateForIssuance(JILjava/util/ArrayList;Z)I")
    source = remove_method(
        source,
        "sehSetCallbackEx(Lvendor/samsung/hardware/biometrics/face/V3_0/ISehBiometricsFaceClientCallback;)Landroid/hardware/biometrics/face/V1_0/OptionalUint64;",
    )
    source = adapt_interface(source, "TestHal", "ISehBiometricsFace")
    if "sehAuthenticateForIssuance" in source or "sehSetCallbackEx" in source:
        raise DonorMismatch("TestHal: unsupported V3 API survives")
    return source


def adapt_dir(directory: Path) -> None:
    sources = {}
    for name, path in CLASS_PATHS.items():
        full = directory / path
        if not full.is_file():
            raise DonorMismatch(f"missing decoded donor class: {full}")
        sources[name] = full.read_text(encoding="utf-8")
    handler = sources["AidlResponseHandler"]
    for needle in (
        "SemFaceServiceExImpl$$ExternalSyntheticLambda6;",
        "SemFaceServiceExImpl$$ExternalSyntheticLambda6;->f$1:[I",
    ):
        if needle not in handler:
            raise DonorMismatch(f"AidlResponseHandler: missing actual Lambda6 callback: {needle}")
    if "SemFaceServiceExImpl$$ExternalSyntheticLambda5;" in handler:
        raise DonorMismatch("AidlResponseHandler: donor synthetic lambda changed")
    changes = {
        "FaceAuthenticationClient": adapt_auth(sources["FaceAuthenticationClient"]),
        "HidlToAidlCallbackConverter": adapt_callback(sources["HidlToAidlCallbackConverter"]),
        "TestHal": adapt_test_hal(sources["TestHal"]),
    }
    for name, data in changes.items():
        if data == sources[name]:
            raise DonorMismatch(f"{name}: expected changes were not made")
    # No writes until every donor invariant has been validated.
    for name, data in changes.items():
        (directory / CLASS_PATHS[name]).write_text(data, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    filt = sub.add_parser("filter")
    filt.add_argument("original", type=Path)
    filt.add_argument("output", type=Path)
    adapt = sub.add_parser("adapt")
    adapt.add_argument("decoded_services_jar", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "filter":
            args.output.write_text(filter_patch(args.original.read_text(encoding="utf-8")), encoding="utf-8")
        else:
            adapt_dir(args.decoded_services_jar)
    except (OSError, DonorMismatch) as exc:
        print(f"S10 Face HIDL 2.0 adaptation aborted: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
