#!/usr/bin/env python3
"""Guard Android 16 S10+ SecSettings hotspot priority using verified donor classes.

SHA256 values are for complete decoded donor classes from compilation #85.
Reject unexpected classes or methods before writing anything. Preserve
unrelated hotspot backup/restore and ordinary Wi-Fi behavior.
"""
import argparse
import hashlib
from pathlib import Path
import re
import sys

DONOR = {
    'com/samsung/android/settings/wifi/mobileap/WifiApCloudBackupRestore.smali': 'e9afa221c5275ce28a52e61e2089f433a3acb20b8febb52db29806aedd217340',
    'com/samsung/android/settings/wifi/mobileap/WifiApSettings$1.smali': '3e7829ffb934817dc30d9af5b04654dcea5f5a3492f99daccbaa6be06ae7fea5',
    'com/samsung/android/settings/wifi/mobileap/WifiApSmartSwitchBackupRestore.smali': 'e6d2ea180b0109ee9ef902a8343421f54179a573fb52997184f44affb07abd0e',
    'com/samsung/android/settings/wifi/mobileap/smartpriority/WifiApSmartPrioritySwitchController.smali': '27dff9bd3fd8249cc8e8131ecdd12cc6bd7da251a5963354d521a8937d9be794',
    'com/samsung/android/settings/wifi/mobileap/utils/WifiApFrameworkUtils.smali': '84701b9700ae49f42bacf4317765a4d5f3af897751a0256ca984f4da3786d51a',
}
INDEX = 'com/samsung/android/settings/wifi/mobileap/WifiApSettings$1.smali'
CONTROLLER = 'com/samsung/android/settings/wifi/mobileap/smartpriority/WifiApSmartPrioritySwitchController.smali'
UTILS = 'com/samsung/android/settings/wifi/mobileap/utils/WifiApFrameworkUtils.smali'
SMALI_DIR = re.compile(r'smali(?:_classes[1-9][0-9]*)?')


def find_class(root, suffix, digest):
    matches = sorted(d / suffix for d in root.iterdir()
                     if d.is_dir() and SMALI_DIR.fullmatch(d.name) and (d / suffix).is_file())
    if len(matches) != 1:
        raise ValueError(f'{suffix}: expected one donor class, found {len(matches)}')
    path = matches[0]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f'{suffix}: unverified donor digest')
    content = data.decode('utf-8')
    descriptor = 'L' + suffix.removesuffix('.smali') + ';'
    if (not content.endswith('\n') or
            len(re.findall(r'^\.class [^\n]*' + re.escape(descriptor) + r'$', content, re.M)) != 1 or
            len(re.findall(r'^\.method ', content, re.M)) != len(re.findall(r'^\.end method$', content, re.M))):
        raise ValueError(f'{suffix}: malformed smali')
    return path, content


def method(text, signature, replacement, required):
    found = list(re.finditer(r'^\.method [^\n]*' + re.escape(signature) +
                            r'\n.*?^\.end method$', text, re.M | re.S))
    if len(found) != 1:
        raise ValueError(f'{signature}: expected one method')
    match = found[0]
    body = match.group()
    if any(body.count(token) != 1 for token in required):
        raise ValueError(f'{signature}: donor wiring changed')
    header = body.split('\n', 1)[0]
    new = header + '\n    .locals 0\n\n' + replacement + '\n.end method'
    return text[:match.start()] + new + text[match.end():]


def adapt_index(text):
    sig = 'getRawDataToIndex(Landroid/content/Context;)Ljava/util/List;'
    found = list(re.finditer(r'^\.method [^\n]*' + re.escape(sig) +
                            r'\n.*?^\.end method$', text, re.M | re.S))
    if len(found) != 1:
        raise ValueError('search index method missing or duplicated')
    match = found[0]
    body = match.group()
    if (body.count('"smart_priority_switch_preference"') != 1 or
            body.count('"guest_mode_switch_preference"') != 1 or
            body.count('    :cond_2\n') != 1 or
            body.count('    return-object p0\n') != 2):
        raise ValueError('unexpected priority search layout')
    tail = re.search(r'    :cond_2\n(.*?)    return-object p0\n\.end method$', body, re.S)
    if not tail or tail.group(1).count('SearchIndexableRaw;') < 2 or \
            tail.group(1).count('"smart_priority_switch_preference"') != 1:
        raise ValueError('priority search entry not isolated')
    return text[:match.start()] + body[:tail.start()] + \
        '    :cond_2\n    return-object p0\n.end method' + text[match.end():]


def run(root, check=False):
    if not root.is_dir():
        raise ValueError('decoded SecSettings directory missing')
    original = {suffix: find_class(root, suffix, digest) for suffix, digest in DONOR.items()}
    ctrl = original[CONTROLLER][1]
    ctrl = method(ctrl, 'getAvailabilityStatus()I', '    const/4 p0, 0x3\n\n    return p0',
                  ['isMobileDataUsageSupported(Landroid/content/Context;)Z'])
    ctrl = method(ctrl, 'isChecked()Z', '    const/4 p0, 0x0\n\n    return p0',
                  ['"wifi_ap_smart_priority_enable"'])
    ctrl = method(ctrl, 'setChecked(Z)Z', '    const/4 p0, 0x0\n\n    return p0',
                  ['setPrioritizeRealTimeTrafficDB(Landroid/content/Context;Z)V'])
    utils = original[UTILS][1]
    utils = method(utils, 'isPrioritizeRealTimeTrafficOn(Landroid/content/Context;)Z',
                   '    const/4 p0, 0x0\n\n    return p0', ['"wifi_ap_smart_priority_enable"'])
    utils = method(utils, 'setPrioritizeRealTimeTrafficDB(Landroid/content/Context;Z)V',
                   '    return-void', ['"wifi_ap_smart_priority_enable"'])
    planned = {CONTROLLER: ctrl, UTILS: utils, INDEX: adapt_index(original[INDEX][1])}
    for suffix, new in planned.items():
        old = original[suffix][1]
        if (new == old or not new.endswith('\n') or
                len(re.findall(r'^\.method ', new, re.M)) != len(re.findall(r'^\.end method$', new, re.M))):
            raise ValueError(f'{suffix}: invalid output')
    if not check:
        for suffix, new in planned.items():
            original[suffix][0].write_text(new, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded_apk', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        run(args.decoded_apk, args.check)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f'S10 Android 16 SecSettings priority adaptation rejected donor: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
