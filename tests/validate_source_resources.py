#!/usr/bin/env python3
"""Syntax-check every tracked XML, JSON, and Python blob, including sparse-excluded files.

This only validates syntax, not Android resource semantics or API compatibility.
"""
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.xml", "*.json", "*.py"],
        check=True, capture_output=True,
    )
    return [p.decode("utf-8") for p in result.stdout.split(b"\0") if p]


def main() -> int:
    checked = {"json": 0, "xml": 0, "py": 0}
    errors = []
    for path in tracked_paths():
        ext = Path(path).suffix.lstrip(".")
        try:
            blob = subprocess.run(
                ["git", "show", f"HEAD:{path}"], check=True, capture_output=True
            ).stdout
            if ext == "json":
                json.loads(blob.decode("utf-8-sig"))
            elif ext == "xml":
                ET.fromstring(blob)
            elif ext == "py":
                compile(blob, path, "exec", dont_inherit=True)
            else:
                continue
            checked[ext] += 1
        except (UnicodeError, ValueError, SyntaxError, ET.ParseError,
                subprocess.CalledProcessError) as exc:
            message = str(exc).replace("\n", " ")
            print(f"SYNTAX ERROR in {path}: {type(exc).__name__}: {message}", flush=True)
            print(f"::error file={path}::{type(exc).__name__}: {message}")
            errors.append(path)

    print("Syntax checked: " + ", ".join(
        f"{amount} {extension}" for extension, amount in sorted(checked.items())
    ))
    print(f"Syntax failures: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
