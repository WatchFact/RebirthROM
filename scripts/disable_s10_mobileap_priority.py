#!/usr/bin/env python3
"""Guarded Android 16 S10 MobileAP traffic-priority adaptation."""
import argparse
from pathlib import Path
import re
import sys

PROXY = 'com/samsung/android/server/wifi/SemWifiManagerProxy.smali'
RESET = 'com/samsung/android/server/wifi/ap/SemSettingsSoftResetHandler.smali'
RECEIVER = 'com/samsung/android/server/wifi/ap/SemWifiApBroadcastReceiver.smali'


def find_class(root, suffix):
    matches = sorted(d / suffix for d in root.iterdir()
                     if d.is_dir() and re.fullmatch(r'smali(?:_classes[1-9][0-9]*)?', d.name)
                     and (d / suffix).is_file())
    if len(matches) != 1:
        raise ValueError(f'{suffix}: expected one donor class, found {len(matches)}')
    path = matches[0]
    text = path.read_text(encoding='utf-8')
    descriptor = 'L' + suffix.removesuffix('.smali') + ';'
    if (not text.endswith('\n') or
            len(re.findall(r'^\.class [^\n]*' + re.escape(descriptor) + r'$', text, re.M)) != 1 or
            len(re.findall(r'^\.method ', text, re.M)) != len(re.findall(r'^\.end method$', text, re.M))):
        raise ValueError(f'{suffix}: malformed donor class')
    return path, text


def method(text, signature):
    matches = list(re.finditer(r'^\.method [^\n]*' + re.escape(signature) +
                               r'\n.*?^\.end method$', text, re.M | re.S))
    if len(matches) != 1:
        raise ValueError(f'{signature}: expected one method, found {len(matches)}')
    return matches[0]


def adapt_proxy(text):
    match = method(text, 'isWifiApSmartPrioritySupported()Z')
    body = match.group()
    if not re.fullmatch(
        r'\.method public isWifiApSmartPrioritySupported\(\)Z\n'
        r'\s*\.locals 0\n\s*const/4 p0, 0x1\n\s*return p0\n\.end method', body
    ):
        raise ValueError('unexpected priority support probe')
    return text[:match.start()] + body.replace('const/4 p0, 0x1', 'const/4 p0, 0x0') + text[match.end():]


def validate_reset(text):
    body = method(text, 'resetHotspotSettings()V').group()
    if (body.count('"wifi_ap_smart_priority_enable"') != 1 or
            'Settings$Secure;->putInt(Landroid/content/ContentResolver;Ljava/lang/String;I)Z' not in body or
            '    const/4 v3, 0x0\n' not in body):
        raise ValueError('hotspot reset no longer clears priority setting')


def adapt_receiver(text):
    telemetry = method(text, 'addTheSmartHotspotInfo(Lorg/json/JSONObject;)V').group()
    if (text.count('->getTrafficPriorityStatus()Ljava/lang/String;') != 1 or
            '    const-string v0, "mh_tp"\n' not in telemetry):
        raise ValueError('unexpected hotspot telemetry wiring')
    match = method(text, 'getTrafficPriorityStatus()Ljava/lang/String;')
    body = match.group()
    expected = ('getSemWifiApTrafficPriority()Lcom/samsung/android/server/wifi/ap/smartprio/SemWifiApTrafficPriority;',
                'getmIsPriorityFeatureEnableDuringSession()Z', 'getNRTTrafficEnable()Z',
                'getRTTrafficEnable()Z', '"tp_rt"', '"tp_nrt"',
                '"tp_on_below_cutoff"', '"tp_off"', '"handleWifiApState: "')
    if (not body.startswith('.method public final getTrafficPriorityStatus()Ljava/lang/String;\n    .locals 2\n') or
            any(body.count(token) != 1 for token in expected) or
            body.count('    return-object p0\n') != 1 or
            re.search(r'^\s*\.(?:catch|try_)', body, re.M)):
        raise ValueError('unexpected traffic-priority status method')
    replacement = ('.method public final getTrafficPriorityStatus()Ljava/lang/String;\n'
                   '    .locals 0\n\n    const-string p0, "not_support"\n\n'
                   '    return-object p0\n.end method')
    return text[:match.start()] + replacement + text[match.end():]


def run(decoded: Path, check=False):
    if not decoded.is_dir():
        raise ValueError('decoded semwifi-service.jar directory missing')
    proxy_path, proxy = find_class(decoded, PROXY)
    _, reset = find_class(decoded, RESET)
    receiver_path, receiver = find_class(decoded, RECEIVER)
    validate_reset(reset)
    planned = [(proxy_path, proxy, adapt_proxy(proxy)),
               (receiver_path, receiver, adapt_receiver(receiver))]
    for path, before, after in planned:
        if (before == after or not after.endswith('\n') or
                len(re.findall(r'^\.method ', after, re.M)) !=
                len(re.findall(r'^\.end method$', after, re.M))):
            raise ValueError(f'{path}: invalid adaptation')
    if not check:
        for path, _, after in planned:
            path.write_text(after, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded_jar', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        run(args.decoded_jar, check=args.check)
    except (OSError, ValueError) as exc:
        print(f'S10 MobileAP traffic-priority adaptation rejected donor: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
