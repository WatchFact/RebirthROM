#!/usr/bin/env python3
"""Capture complete, bounded donor smali for a failed Settings virtual-vibration patch.

Read-only diagnostic collector. It does not modify an APK or apply any patch.
Reject incomplete, ambiguous, or unexpectedly large evidence rather than
publishing excerpts that could be mistaken for sufficient rebase evidence.
"""
import argparse
import hashlib
from pathlib import Path
import re
import sys

DIFF = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)
SMALI_DIR = re.compile(r"smali(?:_classes[1-9][0-9]*)?")
MAX_CLASS_BYTES = 1_000_000
MAX_TOTAL_BYTES = 2_000_000
MAX_CLASSES = 20


def capture(decoded: Path, patch: str) -> str:
    if not decoded.is_dir():
        raise ValueError(f"decoded APK directory missing: {decoded}")
    paths = DIFF.findall(patch)
    if not paths or len(paths) > MAX_CLASSES:
        raise ValueError(f"expected 1-{MAX_CLASSES} patch file diffs; found {len(paths)}")
    evidence = []
    total = 0
    seen = set()
    for source, dest in paths:
        parts = Path(source).parts
        if source != dest or len(parts) < 3 or not SMALI_DIR.fullmatch(parts[0]) or ".." in parts:
            raise ValueError(f"unsupported or unsafe smali patch path: {source} -> {dest}")
        suffix = Path(*parts[1:])
        if suffix in seen:
            raise ValueError(f"duplicate patch class: {suffix}")
        seen.add(suffix)
        matches = sorted(
            d / suffix for d in decoded.iterdir()
            if d.is_dir() and SMALI_DIR.fullmatch(d.name) and (d / suffix).is_file()
        )
        if len(matches) != 1:
            raise ValueError(f"expected exactly one donor class for {suffix}; found {len(matches)}")
        path = matches[0]
        size = path.stat().st_size
        if size > MAX_CLASS_BYTES or total + size > MAX_TOTAL_BYTES:
            raise ValueError(f"complete donor class evidence exceeds byte limits: {suffix}")
        data = path.read_bytes()
        try:
            contents = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"non-UTF-8 donor smali: {suffix}") from exc
        if not contents.endswith("\n"):
            raise ValueError(f"donor class missing final newline: {suffix}")
        if not contents.lstrip().startswith(".class ") and "\n.class " not in contents:
            raise ValueError(f"donor class declaration missing: {suffix}")
        if contents.count(".method ") != contents.count(".end method"):
            raise ValueError(f"unbalanced donor smali method declarations: {suffix}")
        evidence.append((path.relative_to(decoded).as_posix(), contents,
                         hashlib.sha256(data).hexdigest()))
        total += len(data)
    output = [f"Donor APK: {decoded}", f"Patch classes: {len(evidence)}",
              "Read-only full-class evidence; no patch applied."]
    for path, contents, digest in evidence:
        output.extend([f"===== BEGIN {path} sha256={digest} =====", contents.rstrip("\n"),
                       f"===== END {path} ====="])
    return "\n".join(output) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decoded_apk", type=Path)
    parser.add_argument("source_patch", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = capture(args.decoded_apk, args.source_patch.read_text(encoding="utf-8"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"S10 Settings virtual-vibration evidence capture failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
