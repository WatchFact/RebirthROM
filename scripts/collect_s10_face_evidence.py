#!/usr/bin/env python3
"""Read-only, bounded donor evidence for the S10 legacy Face HIDL 2.0 patch.

The Android 16 services.jar bytecode differs from the legacy patch. Capture
actual classes and call sites instead of guessing face authentication logic.
"""
import argparse
from pathlib import Path, PurePosixPath
import re

DIFF = re.compile(r"^diff --git a/(smali(?:_classes[0-9]+)?/[^\n]+\.smali) b/\1$", re.MULTILINE)
NEEDLES = (
    "V3_0/ISehBiometricsFace", "V2_0/ISehBiometricsFace",
    "sehAuthenticateForIssuance", "HidlToAidl", "mIsAuthenticationExtOperation",
    "SemFaceServiceExImpl", "mHandlerMain", "HidlMemory",
    "FEATURE_JDM_HAL", "authenticate BILG", "mCallback",
)
MAX_METHODS = 6
MAX_LINES = 190
MAX_LAMBDAS = 12
MAX_LAMBDA_LINES = 160
# Complete method bodies, not arbitrary excerpts, are needed to rebase
# Android 16 switch tables and exception/branch labels without guessing.
# Limit this to the four verified failing classes and bounded method lengths.
FULL_METHOD_ANCHORS = {
    "AidlResponseHandler.smali": ("SemFaceServiceExImpl$ExternalSyntheticLambda6",),
    "FaceAuthenticationClient.smali": ("authenticate BILG",),
    "HidlToAidlCallbackConverter.smali": ("onTransact(",),
    "TestHal.smali": ("onTransact(",),
}
MAX_FULL_METHOD_LINES = 1600
MAX_FULL_METHODS_PER_CLASS = 2


def patch_classes(patch_text: str) -> list[str]:
    names = []
    for match in DIFF.finditer(patch_text):
        rel = PurePosixPath(match.group(1))
        if ".." in rel.parts or not rel.parts[0].startswith("smali"):
            raise ValueError("unsafe patch path")
        if str(rel) not in names:
            names.append(str(rel))
    if not names:
        raise ValueError("no smali class diffs found in face patch")
    return names


def matching_class(decoded: Path, rel: str) -> list[Path]:
    tail = rel.split("/", 1)[1]
    return sorted(p for p in decoded.glob("smali*/" + tail) if p.is_file())


def excerpt(lines: list[str], limit: int, focus: int) -> list[str]:
    lo = max(0, focus - limit // 3)
    hi = min(len(lines), lo + limit)
    return [f"{i + 1}: {lines[i]}" for i in range(lo, hi)]


def capture(decoded: Path, patch_text: str) -> str:
    if not decoded.is_dir():
        raise ValueError(f"decoded services.jar directory missing: {decoded}")
    report = ["S10 face HIDL 2.0 patch mismatch: donor smali evidence",
              "Read-only excerpts; no patch was applied or skipped."]
    for rel in patch_classes(patch_text):
        matches = matching_class(decoded, rel)
        report.append("\n## " + rel)
        report.append(f"Matching decoded classes: {len(matches)}")
        if len(matches) != 1:
            report.extend(str(p.relative_to(decoded)) for p in matches[:8])
            continue
        path = matches[0]
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        report.append(f"Actual path: {path.relative_to(decoded)}; lines: {len(lines)}")
        report.extend(f"{i + 1}: {line}" for i, line in enumerate(lines[:45]))
        methods = []
        start = None
        for i, line in enumerate(lines):
            if line.startswith(".method "):
                start = i
            elif line == ".end method" and start is not None:
                hits = [j for j in range(start, i + 1)
                        if any(n in lines[j] for n in NEEDLES)]
                if hits:
                    score = sum(sum(1 for n in NEEDLES if n in lines[j]) for j in hits)
                    methods.append((score, start, i + 1, hits))
                start = None
        report.append(f"Matching methods: {len(methods)}")
        for _, start, end, hits in sorted(methods, key=lambda x: (-x[0], x[1]))[:MAX_METHODS]:
            report.append(f"Method at {start + 1}: {lines[start]}; ends at {end}")
            report.extend(f"{j + 1}: {lines[j]}" for j in range(start, min(start + 12, end)))
            # Capture first and last relevant sites when large methods differ.
            focuses = [hits[0]]
            if hits[-1] - hits[0] > MAX_LINES:
                focuses.append(hits[-1])
            for focus in focuses:
                lo = max(start, focus - MAX_LINES // 3)
                hi = min(end, lo + MAX_LINES)
                report.append(f"Excerpt {lo + 1}-{hi}")
                report.extend(f"{j + 1}: {lines[j]}" for j in range(lo, hi))
        anchors = FULL_METHOD_ANCHORS.get(path.name, ())
        full_count = 0
        for _, start, end, _ in sorted(methods, key=lambda x: x[1]):
            if full_count >= MAX_FULL_METHODS_PER_CLASS:
                break
            body = lines[start:end]
            if not any(anchor in line for anchor in anchors for line in body):
                continue
            report.append(f"Complete method evidence at {start + 1}: {lines[start]}; ends at {end}")
            if end - start > MAX_FULL_METHOD_LINES:
                report.append(f"Method exceeds {MAX_FULL_METHOD_LINES} lines; not exported")
                continue
            report.extend(f"{j + 1}: {lines[j]}" for j in range(start, end))
            full_count += 1
    # Synthetic lambda numbering changes between Samsung donor revisions.
    # Inventory only the exact face-service lambda family for safe rebasing.
    lambdas = sorted(p for p in decoded.glob(
        "smali*/com/android/server/biometrics/sensors/face/aidl/"
        "SemFaceServiceExImpl$$ExternalSyntheticLambda*.smali") if p.is_file())
    report.append(f"\n## Face service synthetic lambda inventory: {len(lambdas)}")
    for path in lambdas[:MAX_LAMBDAS]:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        report.append(f"Path: {path.relative_to(decoded)}; lines: {len(lines)}")
        report.extend(f"{i + 1}: {line}" for i, line in enumerate(lines[:MAX_LAMBDA_LINES]))
        if len(lines) > MAX_LAMBDA_LINES:
            report.append(f"Truncated after {MAX_LAMBDA_LINES} lines")
    return "\n".join(report) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decoded_services", type=Path)
    parser.add_argument("face_patch", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        content = capture(args.decoded_services, args.face_patch.read_text(encoding="utf-8"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"S10 face evidence collection failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
