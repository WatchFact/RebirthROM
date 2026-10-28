#!/usr/bin/env python3
"""Read-only audit of S10 light HAL binary, init and VINTF wiring.

The donor light binary may be installed without the service declarations it
needs. This tool records evidence, not a claim that the service will boot.
"""
import argparse
import json
from pathlib import Path
import re

PATTERN = re.compile(r"(?:android|vendor\.samsung)\.hardware\.light|light-service|\blights?\b", re.I)
MAX_FILE = 2 * 1024 * 1024
MAX_MATCHES = 100


def inspect_root(root: Path) -> dict:
    evidence = {"root": str(root), "root_exists": root.is_dir() and not root.is_symlink(),
                "matches": [], "light_service_binary": "not found"}
    if not evidence["root_exists"]:
        return evidence
    binary = root / "vendor/bin/hw/vendor.samsung.hardware.light-service"
    if binary.is_file() and not binary.is_symlink():
        evidence["light_service_binary"] = "present"
    elif binary.is_symlink():
        evidence["light_service_binary"] = "symlink (not followed)"
    for directory in (root / "vendor/etc/init", root / "vendor/etc/vintf"):
        if not directory.is_dir() or directory.is_symlink():
            continue
        for file in sorted(directory.rglob("*")):
            if not file.is_file() or file.is_symlink() or file.suffix not in (".rc", ".xml"):
                continue
            if file.stat().st_size > MAX_FILE:
                evidence["matches"].append({"path": str(file.relative_to(root)),
                                            "error": "oversized config (not read)"})
                continue
            try:
                lines = file.read_text(encoding="utf-8").splitlines()
            except UnicodeError:
                evidence["matches"].append({"path": str(file.relative_to(root)),
                                            "error": "non-UTF-8 config (not read)"})
                continue
            for number, line in enumerate(lines, 1):
                if PATTERN.search(line):
                    evidence["matches"].append({"path": str(file.relative_to(root)),
                                                "line": number, "text": line.strip()[:240]})
                    if len(evidence["matches"]) >= MAX_MATCHES:
                        evidence["truncated"] = True
                        return evidence
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("roots", nargs="+", type=Path)
    args = parser.parse_args()
    result = {"note": "Read-only source evidence; hardware compatibility and boot unverified",
              "roots": [inspect_root(root) for root in args.roots]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
