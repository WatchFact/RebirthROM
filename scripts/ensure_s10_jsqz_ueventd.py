#!/usr/bin/env python3
"""Preserve S10 vendor ueventd rules at Android 16's imported path.

Stock S10 firmware may contain only /vendor/ueventd.rc, or neither path.
Preserve legacy rules when migrating, and reject conflicting permissions.
"""
from pathlib import Path
import sys

RULE = ("/dev/jsqz", "0660", "mediacodec", "camera")


def ensure_rule(path: Path, legacy: Path | None = None) -> bool:
    if path.is_symlink() or not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError(f"missing or unsafe imported vendor ueventd directory/file: {path}")
    created = not path.exists()
    if not created and not path.is_file():
        raise ValueError(f"unsafe imported vendor ueventd file: {path}")
    if created:
        if legacy is not None and (legacy.is_symlink() or (legacy.exists() and not legacy.is_file())):
            raise ValueError(f"unsafe legacy vendor ueventd file: {legacy}")
        if legacy is not None and legacy.is_file():
            data = legacy.read_bytes().decode("utf-8")
        else:
            data = "# Exynos9820 JSQZ node permission (Android 16 vendor import)\n"
    else:
        data = path.read_bytes().decode("utf-8")
    matches = [line.split() for line in data.splitlines()
               if line.strip() and not line.lstrip().startswith("#")
               and line.split()[0] == RULE[0]]
    if matches:
        if len(matches) != 1 or tuple(matches[0]) != RULE:
            raise ValueError(f"conflicting or duplicate /dev/jsqz rule: {path}")
        if created:
            path.write_bytes(data.encode("utf-8"))
            return True
        return False
    newline = "\r\n" if "\r\n" in data else "\n"
    suffix = "" if not data or data.endswith(("\n", "\r")) else newline
    addition = suffix + " ".join(RULE) + newline
    if created:
        path.write_bytes((data + addition).encode("utf-8"))
    else:
        with path.open("a", encoding="utf-8", newline="") as stream:
            stream.write(addition)
    return True


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("Usage: ensure_s10_jsqz_ueventd.py /vendor/etc/ueventd.rc [/vendor/ueventd.rc]", file=sys.stderr)
        return 2
    try:
        ensure_rule(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) == 3 else None)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"S10 JSQZ ueventd integration failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
