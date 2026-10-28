#!/usr/bin/env python3
"""Fail closed unless the extracted S10 vendor has its own wired AIDL light HAL.

This checks source-file consistency, not hardware compatibility or bootability.
Do not silently replace the Exynos9820 HAL with an unrelated Samsung device's binary.
"""
import argparse
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

BINARY = "vendor/bin/hw/vendor.samsung.hardware.light-service"
INIT = "vendor/etc/init/lights-default-sec.rc"
MANIFEST = "vendor/etc/vintf/manifest/lights-default-sec.xml"
SERVICE = "vendor.samsung.hardware.light-default"
EXECUTABLE = "/" + BINARY


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def verify(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("S10 vendor work directory is missing or a symlink")
    for relative in (BINARY, INIT, MANIFEST):
        path = root / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing, empty or symlinked S10 light HAL file: {relative}")

    # Check that this is an ARM ELF executable, not a donor placeholder.
    with (root / BINARY).open("rb") as f:
        header = f.read(20)
    if (len(header) < 20 or header[:4] != b"\x7fELF"
            or header[4] not in (1, 2) or header[5] != 1
            or int.from_bytes(header[18:20], "little") not in (40, 183)):
        raise ValueError("Stock S10 light-service is not a little-endian ARM ELF")

    services = []
    for line in (root / INIT).read_text(encoding="utf-8").splitlines():
        match = re.match(r"^service\s+(\S+)\s+(\S+)(?:\s|$)", line)
        if match and match.group(1) == SERVICE:
            services.append(match.group(2))
    if services != [EXECUTABLE]:
        raise ValueError("Stock S10 light init service is absent, duplicated or miswired")

    xml = ET.parse(root / MANIFEST).getroot()
    if _local(xml.tag) != "manifest":
        raise ValueError("Stock S10 light VINTF fragment has no manifest root")
    matches = []
    for hal in xml:
        if _local(hal.tag) != "hal":
            continue
        names = [(child.text or "").strip() for child in hal if _local(child.tag) == "name"]
        if "android.hardware.light" not in names:
            continue
        fqnames = [(child.text or "").strip() for child in hal if _local(child.tag) == "fqname"]
        for interface in hal:
            if _local(interface.tag) != "interface":
                continue
            names_i = [(child.text or "").strip() for child in interface if _local(child.tag) == "name"]
            instances = [(child.text or "").strip() for child in interface if _local(child.tag) == "instance"]
            if "ILights" in names_i and "default" in instances:
                fqnames.append("ILights/default")
        matches.append((hal.attrib.get("format"), "ILights/default" in fqnames))
    if matches != [("aidl", True)]:
        raise ValueError("Stock S10 light VINTF must declare one AIDL ILights/default HAL")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path)
    args = parser.parse_args()
    try:
        verify(args.work_dir)
    except (ValueError, ET.ParseError, OSError, UnicodeError) as exc:
        print(f"ERROR: Stock S10 light HAL validation failed: {exc}", file=sys.stderr)
        return 1
    print("Verified native S10 AIDL light HAL files and wiring (boot unverified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
