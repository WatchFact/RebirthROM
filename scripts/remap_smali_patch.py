#!/usr/bin/env python3
"""Relocate a unified smali patch to the dex directories of a decoded APK.

Only diff headers are rewritten. A missing or ambiguous class is fatal; no
patch hunk or bytecode is changed and git apply must still validate the hunks.
"""
import argparse
from pathlib import Path
import re
import sys

SMALI_DIR = re.compile(r"smali(?:_classes[1-9][0-9]*)?")
DIFF = re.compile(r"^diff --git a/(\S+) b/(\S+)(\r?\n?)$")
HEADER = re.compile(r"^(--- a/|\+\+\+ b/)(\S+)(\r?\n?)$")


def remap(decoded: Path, patch: str) -> str:
    if not decoded.is_dir():
        raise ValueError(f"decoded APK directory missing: {decoded}")
    old_paths = []
    for line in patch.splitlines(keepends=True):
        match = DIFF.match(line)
        if match:
            if match.group(1) != match.group(2):
                raise ValueError("renaming patch not supported")
            old_paths.append(match.group(1))
    if not old_paths:
        raise ValueError("no file diffs in patch")
    replacements = {}
    for old in old_paths:
        parts = Path(old).parts
        if len(parts) < 2 or not SMALI_DIR.fullmatch(parts[0]) or ".." in parts:
            raise ValueError(f"unsafe or non-smali path in patch: {old}")
        suffix = Path(*parts[1:])
        matches = sorted(
            directory / suffix for directory in decoded.iterdir()
            if directory.is_dir() and SMALI_DIR.fullmatch(directory.name)
            and (directory / suffix).is_file()
        )
        if len(matches) != 1:
            raise ValueError(f"expected one decoded class for {suffix}; found {len(matches)}: "
                             + ", ".join(str(p.relative_to(decoded)) for p in matches))
        replacements[old] = matches[0].relative_to(decoded).as_posix()
    output = []
    for line in patch.splitlines(keepends=True):
        match = DIFF.match(line)
        if match:
            old = match.group(1)
            output.append(f"diff --git a/{replacements[old]} b/{replacements[old]}{match.group(3)}")
            continue
        match = HEADER.match(line)
        if match:
            old = match.group(2)
            if old not in replacements:
                raise ValueError(f"header path not present in diff: {old}")
            output.append(f"{match.group(1)}{replacements[old]}{match.group(3)}")
            continue
        output.append(line)
    return "".join(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decoded_apk", type=Path)
    parser.add_argument("source_patch", type=Path)
    parser.add_argument("output_patch", type=Path)
    args = parser.parse_args()
    try:
        patch = args.source_patch.read_text(encoding="utf-8")
        adjusted = remap(args.decoded_apk, patch)
        args.output_patch.write_text(adjusted, encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"smali patch remapping failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
