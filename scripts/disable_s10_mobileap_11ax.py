#!/usr/bin/env python3
"""Guarded Android 16 S10 MobileAP 11ax disablement.

The S10 target does not advertise Wi-Fi 6 hotspot support. Restrict the
Android 16 donor's hotspot capability reporting without changing ordinary
Wi-Fi 6 client support or other SoftAP capabilities. Reject changed bytecode.
"""
import argparse
from pathlib import Path
import re
import sys

CLASSES = (
    'com/samsung/android/server/wifi/ap/SemSoftApConfiguration.smali',
    'com/samsung/android/server/wifi/ap/SemWifiApChipInfo.smali',
    'com/samsung/android/server/wifi/ap/SemWifiApChipInfo$SemWifiApChipSupportInfo.smali',
)


def one_method(text, signature):
    pattern = re.compile(r'^\.method [^\n]*' + re.escape(signature) +
                         r'\n.*?^\.end method$', re.M | re.S)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f'{signature}: expected one method, found {len(matches)}')
    return matches[0]


def replace_method(text, signature, transform):
    match = one_method(text, signature)
    return text[:match.start()] + transform(match.group()) + text[match.end():]


def adapt_configuration(text):
    def transform(body):
        if ('    .locals 4\n' not in body or
                body.count('SPF_11ax=true\\n') != 1 or
                'SPF_6G=' not in body):
            raise ValueError('unexpected Android 16 hotspot feature dump')
        return body.replace('SPF_11ax=true\\n', 'SPF_11ax=false\\n', 1)
    return replace_method(text, 'showSecProductFeature()Ljava/lang/String;', transform)


def adapt_chip_info(text):
    def transform(body):
        branch = '    if-eq p1, v0, :cond_2\n'
        if (body.count(branch) != 1 or
                '    .locals 3\n' not in body or
                '    const/4 v0, 0x1\n' not in body or
                '    if-eq p1, v1, :cond_2\n' not in body or
                '    :cond_1\n    return v2\n' not in body or
                '    :cond_2\n    :goto_0\n    return v0\n' not in body or
                'isSupportedSoftApPowerSave()Z' not in body):
            raise ValueError('unexpected Android 16 hotspot capability dispatch')
        # Capability 1 = SoftAP 11ax: route to the existing false return.
        # Capability 2 and power-save capability 3 retain donor behavior.
        return body.replace(branch, '    if-eq p1, v0, :cond_1\n', 1)
    return replace_method(text, 'supportThisSoftApFeature(I)Z', transform)


def adapt_chip_support(text):
    def transform(body):
        if ('.locals 5\n' not in body or
                '->featureArray:[B' not in body or
                '    and-int/2addr p0, v4\n' not in body or
                '    const-string v3, "isSupportedSoftAp11ax : %s"' not in body):
            raise ValueError('unexpected Android 16 chip 11ax probe')
        # A direct query must not re-enable an unsupported target feature.
        header = body.split('\n', 1)[0]
        return (header + '\n    .locals 1\n\n'
                '    const/4 v0, 0x0\n\n    return v0\n.end method')
    return replace_method(text, 'isSupportedSoftAp11ax()Z', transform)


def run(decoded: Path, check=False):
    if not decoded.is_dir():
        raise ValueError('decoded semwifi-service.jar directory missing')
    transforms = (adapt_configuration, adapt_chip_info, adapt_chip_support)
    planned = []
    for suffix, transform in zip(CLASSES, transforms):
        matches = sorted(p for directory in decoded.iterdir()
                         if directory.is_dir() and
                         re.fullmatch(r'smali(?:_classes[1-9][0-9]*)?', directory.name)
                         for p in [directory / suffix] if p.is_file())
        if len(matches) != 1:
            raise ValueError(f'{suffix}: expected one donor class, found {len(matches)}')
        path = matches[0]
        before = path.read_text(encoding='utf-8')
        descriptor = 'L' + suffix[:-6] + ';'
        if (not before.endswith('\n') or
                not re.search(r'^\.class [^\n]*' + re.escape(descriptor) + '$', before, re.M) or
                before.count('.method ') != before.count('.end method')):
            raise ValueError(f'{suffix}: malformed or incompatible class')
        after = transform(before)
        if (after.count('.method ') != after.count('.end method') or
                not after.endswith('\n')):
            raise ValueError(f'{suffix}: invalid transformed class')
        planned.append((path, after))
    # Check all classes before touching any of them; never apply partial hunks.
    if not check:
        for path, after in planned:
            path.write_text(after, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded_jar', type=Path)
    parser.add_argument('--check', action='store_true', help='validate without writing')
    args = parser.parse_args()
    try:
        run(args.decoded_jar, check=args.check)
    except (OSError, ValueError) as exc:
        print(f'S10 Android 16 MobileAP 11ax adaptation rejected donor: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
