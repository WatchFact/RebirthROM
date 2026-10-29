#!/usr/bin/env python3
"""Guarded Android 16 S10 Settings virtual-vibration adaptation.

Disable the unsupported optional sound feature without changing hardware
vibration controls or renumbering Samsung's SoundItem switch tables.
Reject unexpected donor bytecode rather than silently skipping a patch.
"""
import argparse
from pathlib import Path
import re
import sys

CLASSES = {
    'com/samsung/android/settings/asbase/audio/SoundSettings$3.smali': 'search',
    'com/samsung/android/settings/asbase/reset/ResetSoundSystemFeedbackSettings$1.smali': 'reset',
    'com/samsung/android/settings/asbase/vibration/VirtualVibrationSoundPreferenceController.smali': 'controller',
    'com/samsung/android/settings/eternal/provider/items/SoundItem.smali': 'backup',
}


def replace_one(text, before, after, name):
    if text.count(before) != 1:
        raise ValueError(f'{name}: expected one exact donor sequence, found {text.count(before)}')
    return text.replace(before, after, 1)


def method(text, signature):
    matches = list(re.finditer(r'(?m)^\.method [^\n]*' + re.escape(signature) +
                               r'\n.*?^\.end method$', text, re.S | re.M))
    if len(matches) != 1:
        raise ValueError(f'expected one method {signature}, found {len(matches)}')
    return matches[0]


def adapt(text, kind):
    if kind == 'search':
        # Android 16 donor no longer indexes the feature here.
        if 'vibration_sound_enabled' in text or 'VibrationSoundEnabled' in text:
            raise ValueError('SoundSettings search index changed')
        return text
    if kind == 'reset':
        needle = ('    const-string/jumbo p1, "vibration_sound_enabled"\n\n'
                  '    invoke-static {p0, p1, v2}, Landroid/provider/Settings$System;->putInt(Landroid/content/ContentResolver;Ljava/lang/String;I)Z\n\n')
        return replace_one(text, needle, '', 'reset setting')
    if kind == 'controller':
        m = method(text, 'getAvailabilityStatus()I')
        original = '.locals 0\n\n    const/4 p0, 0x0\n\n    return p0'
        if m.group().count(original) != 1:
            raise ValueError('unexpected availability implementation')
        text = text[:m.start()] + m.group().replace(original, original.replace('0x0', '0x3'), 1) + text[m.end():]
        m = method(text, 'setChecked(Z)Z')
        if (m.group().count('"vibration_sound_enabled"') != 1 or
            m.group().count('Settings$System;->putInt(') != 1 or
            'return p0' not in m.group()):
            raise ValueError('unexpected setChecked implementation')
        replacement = (m.group().split('\n', 1)[0] +
                       '\n    .locals 0\n\n    const/4 p0, 0x0\n\n    return p0\n.end method')
        text = text[:m.start()] + replacement + text[m.end():]
        m = method(text, 'setValue(Lcom/samsung/android/settings/cube/ControlValue;)Lcom/samsung/android/settings/cube/ControlResult;')
        body = m.group()
        before = ('    const-string/jumbo v1, "vibration_sound_enabled"\n\n'
                  '    invoke-static {p0, v1, p1}, Landroid/provider/Settings$System;->putInt(Landroid/content/ContentResolver;Ljava/lang/String;I)Z\n\n')
        body = replace_one(body, before, '', 'controller setValue write')
        body = replace_one(body,
                           'Lcom/samsung/android/settings/cube/ControlResult$ResultCode;->SUCCESS:',
                           'Lcom/samsung/android/settings/cube/ControlResult$ResultCode;->FAIL:',
                           'controller setValue result')
        return text[:m.start()] + body + text[m.end():]
    if kind == 'backup':
        # Keep all switch labels and hardware vibration backup paths intact.
        # Neutralize only the optional feature's restore arm.
        pat = re.compile(r'(?m)^    :pswitch_1f\n(?P<body>.*?)(?=^    :pswitch_20\n)', re.S | re.M)
        matches = [m for m in pat.finditer(text) if '"vibration_sound_enabled"' in m.group('body')]
        if len(matches) != 1:
            raise ValueError('expected exactly one virtual-vibration restore switch arm')
        m = matches[0]
        if (m.group('body').count('"vibration_sound_enabled"') != 1 or
            m.group('body').count('Settings$System;->putInt(') != 1 or
            m.group('body').count('return-object p0') != 1):
            raise ValueError('unexpected backup restore arm')
        return text[:m.start()] + '    :pswitch_1f\n    return-object p0\n\n' + text[m.end():]
    raise ValueError('unknown adaptation kind')


def run(decoded: Path):
    if not decoded.is_dir():
        raise ValueError('decoded APK directory missing')
    planned = []
    for suffix, kind in CLASSES.items():
        matches = sorted(p for d in decoded.iterdir() if d.is_dir() and
                         re.fullmatch(r'smali(?:_classes[1-9][0-9]*)?', d.name)
                         for p in [d / suffix] if p.is_file())
        if len(matches) != 1:
            raise ValueError(f'{suffix}: expected one donor class, found {len(matches)}')
        path = matches[0]
        before = path.read_text(encoding='utf-8')
        if not before.endswith('\n') or before.count('.method ') != before.count('.end method'):
            raise ValueError(f'{suffix}: malformed donor class')
        after = adapt(before, kind)
        if after.count('.method ') != after.count('.end method'):
            raise ValueError(f'{suffix}: invalid modified class')
        planned.append((path, after))
    # No writes before all donor classes pass.
    for path, contents in planned:
        path.write_text(contents, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded_apk', type=Path)
    args = parser.parse_args()
    try:
        run(args.decoded_apk)
    except (OSError, ValueError) as exc:
        print(f'S10 Settings virtual-vibration adaptation rejected donor: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
