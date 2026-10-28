#!/usr/bin/env python3
"""Install the Exynos9820 JSQZ device-node rule in Android 16's imported ueventd file.

Android 16 imports /vendor/etc/ueventd.rc, not /vendor/ueventd.rc.
Refuse a missing file or conflicting permission instead of silently creating
an unreferenced configuration or overriding a stock rule.
"""
from pathlib import Path
import sys

RULE = ("/dev/jsqz", "0660", "mediacodec", "camera")


def ensure_rule(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing or unsafe imported vendor ueventd file: {path}")
    data = path.read_bytes().decode("utf-8")
    matches = [line.split() for line in data.splitlines()
               if line.strip() and not line.lstrip().startswith("#")
               and line.split()[0] == RULE[0]]
    if matches:
        if len(matches) != 1 or tuple(matches[0]) != RULE:
            raise ValueError(f"conflicting or duplicate /dev/jsqz rule: {path}")
        return False
    newline = "\r\n" if "\r\n" in data else "\n"
    suffix = "" if not data or data.endswith(("\n", "\r")) else newline
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(suffix + " ".join(RULE) + newline)
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: ensure_s10_jsqz_ueventd.py /path/to/vendor/etc/ueventd.rc", file=sys.stderr)
        return 2
    try:
        ensure_rule(Path(sys.argv[1]))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"S10 JSQZ ueventd integration failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
