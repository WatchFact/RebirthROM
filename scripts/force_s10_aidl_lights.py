#!/usr/bin/env python3
"""Select stock Exynos9820 AIDL ILights instead of the donor's SehLights HAL.

Only the known Android 16 framework layout is accepted. This changes the
framework's HAL selection, not any native service or its binary interface.
"""
import argparse
import re
from pathlib import Path

FLAG = 'Lcom/android/server/power/PowerManagerUtil;->SEC_FEATURE_USE_LIGHTS_HAL_EXTENSION:Z'
ASSIGNMENT = re.compile(r'(?m)^([ \t]*)sput-boolean (v\d+), ' + re.escape(FLAG) + r'$')


def unique_smali(root: Path, name: str) -> Path:
    matches = [p for p in root.glob('smali*/**/' + name) if p.is_file() and not p.is_symlink()]
    if len(matches) != 1:
        raise ValueError(f'{name}: expected one regular donor class, found {len(matches)}')
    return matches[0]


def patch(root: Path) -> bool:
    if not root.is_dir() or root.is_symlink():
        raise ValueError('missing or unsafe decoded services.jar')
    lights = unique_smali(root, 'LightsService.smali').read_text(encoding='utf-8')
    if not all(token in lights for token in (
        FLAG,
        'mVintfLights:Lcom/android/server/lights/LightsService$VintfHalCache;',
        'mVintfSehLights:Lcom/android/server/lights/LightsService$VintfHalCache;',
        'Landroid/hardware/light/ILights$Stub$Proxy;->getLights()',
    )):
        raise ValueError('Android 16 donor lacks the inspected AIDL/SehLights selection paths')
    path = unique_smali(root, 'PowerManagerUtil.smali')
    source = path.read_text(encoding='utf-8')
    if source.count('.method static constructor <clinit>()V') != 1:
        raise ValueError('missing or ambiguous PowerManagerUtil static initializer')
    before, tail = source.split('.method static constructor <clinit>()V', 1)
    if not re.match(r'\s*\.locals 17\s*', tail):
        raise ValueError('unexpected PowerManagerUtil initializer register layout')
    if '.end method' not in tail:
        raise ValueError('unterminated PowerManagerUtil static initializer')
    body, after = tail.split('.end method', 1)
    matches = list(ASSIGNMENT.finditer(body))
    if len(matches) != 1:
        raise ValueError(f'expected exactly one lights extension assignment, found {len(matches)}')
    match = matches[0]
    reg = match.group(2)
    if int(reg[1:]) > 255:
        raise ValueError('HAL selector register exceeds const/16 encoding range')
    if re.search(r'\b' + re.escape(reg) + r'\b', body[match.end():]):
        raise ValueError('HAL selector register is live after assignment; refusing rewrite')
    previous = body[:match.start()]
    if re.search(r'(?m)^\s*const/16 ' + re.escape(reg) + r', 0x0\s*$', previous[-100:]):
        return False
    replacement = f'{match.group(1)}const/16 {reg}, 0x0\n\n{match.group(0)}'
    updated = before + '.method static constructor <clinit>()V' + body[:match.start()] + replacement + body[match.end():] + '.end method' + after
    path.write_text(updated, encoding='utf-8')
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded_services_jar', type=Path)
    args = parser.parse_args()
    changed = patch(args.decoded_services_jar)
    print('S10 native AIDL ILights selected' if changed else 'S10 native AIDL ILights already selected')


if __name__ == '__main__':
    main()
