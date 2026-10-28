#!/usr/bin/env python3
"""Disable Android 16 donor virtual-vibration audio on Exynos9820 safely.

The legacy ten-class patch targets an older donor layout and cannot be applied
atomically to the Android 16 firmware. The inspected Android 16 implementation
initializes optional virtual-vibration audio in bootCompleteReady(), and all
callers guard the helper field against null. Leave normal hardware vibration,
Bluetooth routing, and fold-state initialization intact by omitting only that
optional helper initialization. Fail closed on an unknown donor layout.
"""

import argparse
import hashlib
from pathlib import Path
import re

SERVICE = 'com/android/server/vibrator/VibratorManagerService.smali'
FIELD = ('Lcom/android/server/vibrator/VibratorManagerService;'
         '->mVirtualVibSoundHelper:Lcom/android/server/vibrator/VirtualVibSoundHelper;')
START = '.method public final bootCompleteReady()V'
EXPECTED_METHOD_SHA256 = '18e61f14ef56c7e48dcddb589ab1b08afce40da24b658afbec04593717861f3c'
PATCHED_METHOD = '''.method public final bootCompleteReady()V
    .locals 0

    invoke-virtual {p0}, Lcom/android/server/vibrator/VibratorManagerService;->registerFoldStateListener()V

    return-void
.end method'''
METHOD = re.compile(r'(?ms)^' + re.escape(START) + r'\n.*?^\.end method$')
GET = re.compile(r'^iget-object (v\d+|p\d+), [vp]\d+, ' + re.escape(FIELD) + r'$')
PUT = re.compile(r'^iput-object [vp]\d+, [vp]\d+, ' + re.escape(FIELD) + r'$')
GUARD = re.compile(r'^if-eqz (v\d+|p\d+), :[\w]+$')


def disable(root: Path) -> bool:
    if not root.is_dir() or root.is_symlink():
        raise ValueError('decoded services.jar missing or unsafe')
    matches = list(root.glob('smali*/' + SERVICE))
    if len(matches) != 1 or not matches[0].is_file() or matches[0].is_symlink():
        raise ValueError(f'expected one regular VibratorManagerService class, found {len(matches)}')
    manager = matches[0]
    source = manager.read_text(encoding='utf-8')
    found = list(METHOD.finditer(source))
    if len(found) != 1:
        raise ValueError(f'expected one bootCompleteReady method, found {len(found)}')
    old = found[0].group()
    if old != PATCHED_METHOD:
        digest = hashlib.sha256(old.encode('utf-8')).hexdigest()
        if digest != EXPECTED_METHOD_SHA256:
            raise ValueError('unknown Android 16 bootCompleteReady layout; refusing virtual-vibration rebase')

    # Every helper access must be guarded. In particular, leaving the field
    # null must not introduce an NPE in the vibration service or its callbacks.
    references = 0
    writes = 0
    for path in root.glob('smali*/**/*.smali'):
        if path.is_symlink():
            raise ValueError(f'unsafe smali symlink: {path}')
        data = path.read_text(encoding='utf-8')
        if FIELD not in data:
            continue
        lines = data.splitlines()
        for i, line in enumerate(lines):
            if FIELD not in line:
                continue
            instruction = line.strip()
            if instruction.startswith('.field '):
                continue
            references += 1
            if PUT.fullmatch(instruction):
                writes += 1
                if path != manager or instruction not in old:
                    raise ValueError(f'unexpected virtual-vibration helper assignment in {path}')
            else:
                read = GET.fullmatch(instruction)
                if not read:
                    raise ValueError(f'unrecognized virtual-vibration field access in {path}')
                next_instruction = next((v.strip() for v in lines[i + 1:]
                                         if v.strip() and not v.lstrip().startswith('#')), '')
                guard = GUARD.fullmatch(next_instruction)
                if not guard or guard.group(1) != read.group(1):
                    raise ValueError(f'unguarded virtual-vibration helper access in {path}:{i + 1}')
    if references < (1 if old == PATCHED_METHOD else 2) or (writes != (0 if old == PATCHED_METHOD else 1)):
        raise ValueError(f'unexpected helper reference count ({references}) or writes ({writes})')
    if old == PATCHED_METHOD:
        return False
    updated = source[:found[0].start()] + PATCHED_METHOD + source[found[0].end():]
    manager.write_text(updated, encoding='utf-8')
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded_services_jar', type=Path)
    args = parser.parse_args()
    try:
        changed = disable(args.decoded_services_jar)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(1, f'S10 virtual-vibration rebase rejected: {exc}\n')
    print('S10 virtual-vibration audio disabled; hardware vibration retained' if changed
          else 'S10 virtual-vibration audio already disabled')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
