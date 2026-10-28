#!/usr/bin/env python3
"""Add required S10 vendor feature declarations without damaging permissions XML."""

import argparse
import os
from pathlib import Path
import re
import stat
import tempfile
import xml.etree.ElementTree as ET

FEATURES = (
    "android.hardware.security.model.compatible",
    "android.software.controls",
)
CLOSING_TAG = re.compile(r"(?m)^[ \t]*</permissions\s*>[ \t]*(?=\r?$)")


def ensure_features(path: Path) -> bool:
    original = path.read_bytes()
    # Strict UTF-8 and XML parsing must succeed before touching the file.
    source = original.decode("utf-8")
    root = ET.fromstring(source)
    if root.tag != "permissions":
        raise ValueError("expected <permissions> document root")
    existing = {node.get("name") for node in root.iter("feature")}
    missing = [feature for feature in FEATURES if feature not in existing]
    if not missing:
        return False

    closing = list(CLOSING_TAG.finditer(source))
    if len(closing) != 1:
        raise ValueError("expected one standalone </permissions> closing tag")
    # Preserve all original content, including XML declaration, comments,
    # ordering, and any whitespace or comments after the root element.
    pos = closing[0].start()
    prefix = "" if pos == 0 or source[pos - 1] == "\n" else "\n"
    addition = prefix + "".join(f'    <feature name="{name}"/>\n' for name in missing)
    result = source[:pos] + addition + source[pos:]
    ET.fromstring(result)

    old_mode = stat.S_IMODE(path.stat().st_mode)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(result.encode("utf-8"))
        temporary.chmod(old_mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xml", type=Path)
    args = parser.parse_args()
    changed = ensure_features(args.xml)
    print("Added missing vendor feature declarations" if changed else "Vendor feature declarations already present")


if __name__ == "__main__":
    main()
