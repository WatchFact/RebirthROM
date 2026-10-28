#!/usr/bin/env python3
"""Read-only audit of S10 light HAL binary, init and VINTF wiring.

The donor light binary may be installed without the service declarations it
needs. This tool records evidence, not a claim that the service will boot.
"""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

PATTERN = re.compile(r"(?:android|vendor\.samsung)\.hardware\.light|light-service|\blights?\b", re.I)
MAX_FILE = 2 * 1024 * 1024
MAX_MATCHES = 100



def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _light_manifest_entries(file: Path) -> tuple[list[dict], str | None]:
    """Record actual HAL format/version/instance; never infer compatibility."""
    try:
        root = ET.parse(file).getroot()
    except (ET.ParseError, OSError) as exc:
        return [], f"Cannot parse VINTF XML: {type(exc).__name__}"
    declarations = []
    for hal in root.iter():
        if _local_name(hal.tag) != "hal":
            continue
        children = list(hal)
        names = [(child.text or "").strip() for child in children
                 if _local_name(child.tag) == "name"]
        if not any("hardware.light" in name for name in names):
            continue
        interfaces = []
        for interface in children:
            if _local_name(interface.tag) != "interface":
                continue
            interfaces.append({
                "name": next(((x.text or "").strip() for x in interface
                              if _local_name(x.tag) == "name"), ""),
                "instances": [(x.text or "").strip() for x in interface
                              if _local_name(x.tag) == "instance"],
            })
        declarations.append({
            "format": hal.attrib.get("format", "unspecified"),
            "names": names,
            "versions": [(x.text or "").strip() for x in children
                         if _local_name(x.tag) == "version"],
            "transport": [(x.text or "").strip() for x in children
                          if _local_name(x.tag) == "transport"],
            "fqnames": [(x.text or "").strip() for x in children
                        if _local_name(x.tag) == "fqname"],
            "interfaces": interfaces,
        })
    return declarations, None


def _light_init_services(lines: list[str]) -> list[dict]:
    """Capture service executable and declared interfaces from init RC stanzas."""
    services = []
    current = None
    for line in lines:
        service = re.match(r"^\\s*service\\s+(\\S+)\\s+(\\S+)", line)
        if service:
            current = None
            if PATTERN.search(line):
                current = {"name": service.group(1), "executable": service.group(2),
                           "interfaces": []}
                services.append(current)
            continue
        if current:
            interface = re.match(r"^\\s*interface\\s+(.+?)\\s*$", line)
            if interface:
                current["interfaces"].append(interface.group(1))
    return services


def inspect_root(root: Path) -> dict:
    evidence = {"root": str(root), "root_exists": root.is_dir() and not root.is_symlink(),
                "matches": [], "light_service_binary": "not found",
                "hal_declarations": [], "init_services": [], "parse_errors": []}
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
            relative = str(file.relative_to(root))
            if file.suffix == ".xml" and "vintf" in file.parts:
                declarations, error = _light_manifest_entries(file)
                for entry in declarations:
                    evidence["hal_declarations"].append({"path": relative, **entry})
                if error:
                    evidence["parse_errors"].append({"path": relative, "error": error})
            if file.suffix == ".rc":
                for entry in _light_init_services(lines):
                    evidence["init_services"].append({"path": relative, **entry})
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
