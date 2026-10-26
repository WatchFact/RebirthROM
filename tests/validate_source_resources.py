#!/usr/bin/env python3
"""Syntax-check every tracked XML, JSON, and Python blob, including sparse-excluded files.

This only validates syntax, not Android resource semantics or API compatibility.
"""
import json
import re
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


def parse_xml_blob(blob: bytes, path: str) -> None:
    """Validate regular XML plus known sed insertion/append XML fragments.

    Some Android patch assets are sed /matching-anchor/i or /.../a snippets,
    not standalone XML documents. Validate the address and inserted XML.
    """
    value = blob.decode("utf-8-sig")
    first, sep, remainder = value.partition("\n")
    if first.startswith("/") and sep:
        if not re.fullmatch(r"/[^/\r\n]+/[ia]", first):
            raise ValueError(f"Invalid sed XML insert directive: {first!r}")
        if not remainder.strip():
            raise ValueError("Empty XML patch fragment")
        value = (
            '<fragment xmlns:android="http://schemas.android.com/apk/res/android" '
            'xmlns:settings="http://schemas.android.com/apk/res-auto" '
            'xmlns:tools="http://schemas.android.com/tools">'
            + remainder + "</fragment>"
        )
    ET.fromstring(value)


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
                parse_xml_blob(blob, path)
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
