#!/usr/bin/env python3
"""Capture bounded donor-smali evidence for a failed S10 scene patch.

Only the six classes touched by the legacy scene patch are inspected. This
never edits the APK, patch, or ROM work directory.
"""
import argparse
from pathlib import Path

CLASSES = (
    "callback/forwarder/TextDetectionInfoCallbackForwarder.smali",
    "maker/AutoBeautyPhotoMaker.smali",
    "maker/BeautyPhotoMaker.smali",
    "maker/DualBokehPhotoMaker.smali",
    "maker/MakerCallbackManager.smali",
    "maker/SuperNightPhotoMaker.smali",
)
NEEDLES = (
    "SceneDetectionEventCallback",
    "TextDetectionInfoCallbackForwarder",
    "onTextDetectionInfo",
)


def capture(decoded: Path) -> str:
    if not decoded.is_dir():
        raise ValueError(f"decoded APK directory missing: {decoded}")
    report = ["S10 camera patch mismatch: bounded decoded-donor excerpts", "No APK was modified."]
    for suffix in CLASSES:
        relative = "com/samsung/android/camera/core2/" + suffix
        matches = sorted(p for p in decoded.glob("smali*/" + relative) if p.is_file())
        report.append("\n## " + relative)
        if len(matches) != 1:
            report.append(f"Expected one class; found {len(matches)}: " + ", ".join(str(p.relative_to(decoded)) for p in matches))
            continue
        path = matches[0]
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        report.append(f"Path: {path.relative_to(decoded)}; total lines: {len(lines)}")
        report.extend(f"{i + 1}: {line}" for i, line in enumerate(lines[:28]))
        methods = []
        start = None
        for i, line in enumerate(lines):
            if line.startswith(".method "):
                start = i
            elif line == ".end method" and start is not None:
                end = i + 1
                hits = [j for j in range(start, end) if any(n in lines[j] for n in NEEDLES)]
                if hits:
                    methods.append((start, end, hits))
                start = None
        report.append(f"Matching methods: {len(methods)} (up to 6 excerpts)")
        for start, end, hits in methods[:6]:
            focus = hits[0]
            low = max(start, focus - 50)
            high = min(end, focus + 95)
            report.append(f"Method: {lines[start]} at {start + 1}; excerpt {low + 1}-{high}")
            report.extend(f"{i + 1}: {lines[i]}" for i in range(low, high))
    return "\n".join(report) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decoded_apk", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = capture(args.decoded_apk)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"S10 camera evidence collection failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
