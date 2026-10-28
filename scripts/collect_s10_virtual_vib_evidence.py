#!/usr/bin/env python3
"""Collect bounded, read-only Android 16 smali evidence for virtual-vibration rebase.

The upstream virtual-vibration patch touches multiple audio/vibrator classes.
Never apply partial hunks or disable the feature merely to bypass CI failures.
"""
import argparse
from pathlib import Path, PurePosixPath
import re

DIFF = re.compile(r'^diff --git a/(smali(?:_classes[0-9]+)?/[^\n ]+\.smali) b/([^\n ]+\.smali)$', re.M)
KEYWORDS = (
    'virtualvib', 'vibration', 'vibrator', 'onsetbtscoactivedevice',
    'onupdatecommunicationrouteclient', 'onexternalvibrationstart',
    'onbootphase', 'goodcatch', 'mwatch', 'monlywatchconnected',
    'maudiomanager', 'msco', 'issamsungwatch', 'mbluetoothheadset',
    'samsungbroadcastreceiver', 'audiodevicebroker', 'bthelper',
)
MAX_FULL_CLASS_LINES = 1800
MAX_METHOD_LINES = 1700
# Android 16 donor classes can have more than 100 generic vibration methods.
# Preserve enough evidence for feature-specific call sites without truncating
# them behind unrelated vibration handlers.
MAX_METHODS = 32
MAX_CLASS_OUTPUT_LINES = 20000
MAX_TOTAL_LINES = 75000
PRIORITY_TERMS = (
    ('virtualvib', 100),
    ('onlywatchconnected', 80),
    ('issamsungwatch', 80),
    ('onsetbtscoactivedevice', 60),
    ('onupdatecommunicationrouteclient', 60),
    ('onexternalvibrationstart', 60),
    ('goodcatch', 40),
    ('samsungbroadcastreceiver', 40),
)

# These classes are removed by the legacy patch but are not listed in its
# diff. Capture their real donor definitions before considering a rebase.
EXTRA_CLASSES = (
    'smali_classes2/com/android/server/vibrator/VirtualVibSoundHelper.smali',
    'smali_classes2/com/android/server/vibrator/VibratorManagerInternal.smali',
    'smali_classes2/com/android/server/vibrator/VibratorManagerService$SamsungBroadcastReceiver$$ExternalSyntheticLambda1.smali',
    'smali/com/android/server/audio/BtHelper$$ExternalSyntheticLambda0.smali',
)


def patch_classes(patch: str) -> list[str]:
    classes = []
    for match in DIFF.finditer(patch):
        rel, other = match.groups()
        p = PurePosixPath(rel)
        if rel != other or '..' in p.parts or len(p.parts) < 3:
            raise ValueError(f'unsafe or mismatched patch class: {rel}')
        if rel not in classes:
            classes.append(rel)
    if not classes:
        raise ValueError('no smali class diffs found in virtual-vibration patch')
    return classes


def method_ranges(lines: list[str]) -> list[tuple[int, int]]:
    methods = []
    start = None
    for i, line in enumerate(lines):
        if line.startswith('.method '):
            if start is not None:
                raise ValueError('nested .method declarations in donor smali')
            start = i
        elif line == '.end method':
            if start is None:
                raise ValueError('unpaired .end method in donor smali')
            methods.append((start, i + 1))
            start = None
    if start is not None:
        raise ValueError('unterminated .method in donor smali')
    return methods


def capture(decoded: Path, patch: str) -> str:
    if not decoded.is_dir():
        raise ValueError(f'decoded services.jar directory missing: {decoded}')
    output = [
        'S10 Android 16 virtual-vibration compatibility patch: decoded donor evidence',
        'Read-only; no bytecode has been patched, skipped, or substituted.',
    ]
    for rel in dict.fromkeys((*patch_classes(patch), *EXTRA_CLASSES)):
        tail = rel.split('/', 1)[1]
        matches = sorted(p for p in decoded.glob('smali*/' + tail) if p.is_file())
        section = [f'\n## {rel}', f'Donor class matches: {len(matches)}']
        if len(matches) != 1:
            section.extend(f'Path: {p.relative_to(decoded)}' for p in matches[:8])
            section.append('No method evidence: missing or ambiguous class; do not guess a patch.')
        else:
            path = matches[0]
            lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
            section.extend([f'Actual path: {path.relative_to(decoded)}', f'Donor lines: {len(lines)}'])
            methods = method_ranges(lines)
            if len(lines) <= MAX_FULL_CLASS_LINES:
                section.append('Complete class (bounded):')
                section.extend(f'{i + 1}: {line}' for i, line in enumerate(lines))
            else:
                section.append('Large class; selected complete relevant methods and bounded excerpts:')
                section.extend(f'{i + 1}: {line}' for i, line in enumerate(lines[:90]))
                ranked = []
                for start, end in methods:
                    signature = lines[start].lower()
                    body = '\n'.join(lines[start:end]).lower()
                    score = sum(8 for word in KEYWORDS if word in signature)
                    score += sum(1 for word in KEYWORDS if word in body)
                    # Exact virtual-vibration and patch-touched entry points
                    # outrank generic methods that merely mention vibration.
                    score += sum(weight for word, weight in PRIORITY_TERMS if word in body)
                    if score:
                        ranked.append((-score, start, end))
                ranked.sort()
                section.append(f'Matching methods: {len(ranked)}; captured at most {MAX_METHODS}')
                for _, start, end in ranked[:MAX_METHODS]:
                    section.append(f'Method {start + 1}-{end}: {lines[start]}')
                    if end - start <= MAX_METHOD_LINES:
                        section.extend(f'{i + 1}: {lines[i]}' for i in range(start, end))
                    else:
                        section.append(f'Method exceeds {MAX_METHOD_LINES} lines; head/tail only, unsafe to rebase without complete method')
                        section.extend(f'{i + 1}: {lines[i]}' for i in range(start, min(start + 180, end)))
                        section.append('... omitted method middle ...')
                        section.extend(f'{i + 1}: {lines[i]}' for i in range(max(start + 180, end - 180), end))
        if len(section) > MAX_CLASS_OUTPUT_LINES:
            section = section[:MAX_CLASS_OUTPUT_LINES] + ['Class output truncated; full donor evidence required before rebase.']
        if len(output) + len(section) > MAX_TOTAL_LINES:
            output.append('Global output limit reached; remaining classes omitted.')
            break
        output.extend(section)
    return '\n'.join(output) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded_services', type=Path)
    parser.add_argument('patch', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        result = capture(args.decoded_services, args.patch.read_text(encoding='utf-8'))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding='utf-8')
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Virtual vibration donor evidence collection failed: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
