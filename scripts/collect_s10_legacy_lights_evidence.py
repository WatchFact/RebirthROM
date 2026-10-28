#!/usr/bin/env python3
"""Capture complete read-only Android 16 donor smali for the legacy SehLights rebase.

Do not modify bytecode or bypass the legacy compatibility patch on a mismatch.
A missing, ambiguous, malformed or oversized class fails closed.
"""
import argparse
from pathlib import Path

from collect_s10_virtual_vib_evidence import method_ranges, patch_classes

EXTRA_CLASSES = ("smali/com/android/server/lights/LightsService.smali",)
MAX_CLASS_LINES = 30000
MAX_TOTAL_LINES = 120000


def capture(decoded: Path, patch: str) -> str:
    if not decoded.is_dir() or decoded.is_symlink():
        raise ValueError("decoded services.jar directory missing or unsafe")
    classes = tuple(dict.fromkeys((*patch_classes(patch), *EXTRA_CLASSES)))
    if len(classes) < 5:
        raise ValueError("legacy light patch has an unexpected class inventory")
    output = [
        "S10 Android 16 legacy SehLights compatibility evidence",
        "Read-only complete donor classes; no patch has been skipped or rewritten.",
    ]
    for rel in classes:
        tail = rel.split("/", 1)[1]
        matches = sorted(decoded.glob("smali*/" + tail))
        if len(matches) != 1 or not matches[0].is_file() or matches[0].is_symlink():
            raise ValueError(f"missing, ambiguous or unsafe donor class: {rel} ({len(matches)} matches)")
        path = matches[0]
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_CLASS_LINES:
            raise ValueError(f"donor class exceeds {MAX_CLASS_LINES} lines: {rel}")
        method_ranges(lines)
        section = [f"\\n## {rel}", f"Actual path: {path.relative_to(decoded)}",
                   f"Complete donor lines: {len(lines)}"]
        section.extend(f"{i}: {line}" for i, line in enumerate(lines, 1))
        if len(output) + len(section) > MAX_TOTAL_LINES:
            raise ValueError("complete light donor evidence exceeds total line limit")
        output.extend(section)
    return "\\n".join(output) + "\\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decoded_services", type=Path)
    parser.add_argument("patch", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = capture(args.decoded_services, args.patch.read_text(encoding="utf-8"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(1, f"Cannot collect complete legacy light donor evidence: {exc}\\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
