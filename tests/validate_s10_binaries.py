#!/usr/bin/env python3
"""Verify checked-out S10 ELF bytes and segment bounds, not runtime compatibility."""
import hashlib
import struct
import subprocess
from pathlib import Path

entries = subprocess.check_output(['git', 'ls-files', '-s', '-z', '--',
                                  'platform/exynos9820', 'target']).split(b'\0')
count = 0
errors = []
for entry in entries:
    if not entry:
        continue
    meta, raw_path = entry.split(b'\t', 1)
    mode, expected, _ = meta.decode().split()
    path = Path(raw_path.decode())
    if mode == '120000' or not path.is_file():
        continue
    data = path.read_bytes()
    if not data.startswith(b'\x7fELF'):
        continue
    count += 1
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if actual != expected:
        errors.append(f'{path}: checkout differs from Git blob')
    try:
        endian = {1: '<', 2: '>'}[data[5]]
        if data[4] == 2:
            phoff = struct.unpack_from(endian + 'Q', data, 32)[0]
            entsize, n = struct.unpack_from(endian + 'HH', data, 54)
            minimum = 56
            offset_index, size_index, fmt = 8, 32, 'Q'
        elif data[4] == 1:
            phoff = struct.unpack_from(endian + 'I', data, 28)[0]
            entsize, n = struct.unpack_from(endian + 'HH', data, 42)
            minimum = 32
            offset_index, size_index, fmt = 4, 16, 'I'
        else:
            raise ValueError('invalid ELF class')
        if n and (entsize < minimum or phoff + entsize * n > len(data)):
            raise ValueError('program header table outside file')
        for i in range(n):
            start = phoff + i * entsize
            offset = struct.unpack_from(endian + fmt, data, start + offset_index)[0]
            size = struct.unpack_from(endian + fmt, data, start + size_index)[0]
            if size and offset + size > len(data):
                raise ValueError('ELF segment outside file')
    except (KeyError, IndexError, ValueError, struct.error) as exc:
        errors.append(f'{path}: {exc}')
for error in errors:
    print(error)
print(f'Checked {count} S10 ELF files; failures: {len(errors)}')
raise SystemExit(bool(errors) or count == 0)
