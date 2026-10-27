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
    "callback/forwarder/SceneDetectionEventCallbackForwarder.smali",
    "callback/SceneDetectionEventCallback.smali",
    "node/sceneDetection/SceneDetectionNodeBase$NodeCallback.smali",
)
# Android 16 donor scene callbacks can be obfuscated: method names and the
# SceneDetectionEventCallback type need not survive into maker methods. Node
# callback and scene-detection node references provide the actual call sites.
NEEDLES = (
    "SceneDetectionEventCallback",
    "TextDetectionInfoCallbackForwarder",
    "onTextDetectionInfo",
    "SceneDetectionNodeBase$NodeCallback",
    "SceneDetectionNodeBase",
    "sceneDetection",
    "mTextDetectionInfo",
)
MAX_METHODS = 8
MAX_METHOD_LINES = 145
# Android 16 routes scene events through anonymous maker node callbacks,
# rather than the legacy lambda methods. Capture the exact implementation
# before rebasing bytecode; never infer signatures from old patches.
SCENE_NODE_INTERFACE = "Lcom/samsung/android/camera/core2/node/sceneDetection/SceneDetectionNodeBase$NodeCallback;"
MAX_NODE_CALLBACK_CLASSES = 12
MAX_NODE_CALLBACK_LINES = 220


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
        report.extend(f"{i + 1}: {line}" for i, line in enumerate(lines[:42]))
        methods = []
        start = None
        for i, line in enumerate(lines):
            if line.startswith(".method "):
                start = i
            elif line == ".end method" and start is not None:
                end = i + 1
                hits = [j for j in range(start, end) if any(n in lines[j] for n in NEEDLES)]
                if hits:
                    # Prefer scene event and node callback call sites over
                    # unrelated text-detection references in large classes.
                    score = sum(
                        (4 if "SceneDetectionEventCallback" in lines[j] else 0)
                        + (3 if "SceneDetectionNodeBase$NodeCallback" in lines[j] else 0)
                        + (2 if "SceneDetectionNodeBase" in lines[j] else 0)
                        + (1 if "sceneDetection" in lines[j] else 0)
                        for j in hits
                    )
                    methods.append((score, start, end, hits))
                start = None
        selected = sorted(methods, key=lambda m: (-m[0], m[1]))[:MAX_METHODS]
        report.append(f"Matching methods: {len(methods)} (up to {MAX_METHODS} excerpts)")
        for _, start, end, hits in selected:
            focus = next((j for j in hits if "SceneDetection" in lines[j] or "sceneDetection" in lines[j]), hits[0])
            low = max(start, focus - 45)
            high = min(end, low + MAX_METHOD_LINES)
            report.append(f"Method: {lines[start]} at {start + 1}; excerpt {low + 1}-{high}")
            report.extend(f"{i + 1}: {lines[i]}" for i in range(low, high))
    # Inspect only scene-detection node callback implementers, not unrelated
    # inner classes. Keep output bounded and the decoded APK read-only.
    callbacks = []
    for path in sorted(decoded.glob("smali*/com/samsung/android/camera/core2/maker/*PhotoMaker$*.smali")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if f".implements {SCENE_NODE_INTERFACE}" in lines[:60]:
            callbacks.append((path, lines))
    report.append(
        f"\n## SceneDetectionNodeBase callback implementers: {len(callbacks)} "
        f"(up to {MAX_NODE_CALLBACK_CLASSES} classes, {MAX_NODE_CALLBACK_LINES} lines each)"
    )
    for path, lines in callbacks[:MAX_NODE_CALLBACK_CLASSES]:
        report.append(f"Path: {path.relative_to(decoded)}; total lines: {len(lines)}")
        report.extend(f"{i + 1}: {line}" for i, line in enumerate(lines[:MAX_NODE_CALLBACK_LINES]))
        if len(lines) > MAX_NODE_CALLBACK_LINES:
            report.append(f"Truncated after {MAX_NODE_CALLBACK_LINES} lines")
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
