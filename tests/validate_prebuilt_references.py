#!/usr/bin/env python3
"""Audit literal Samsung prebuilt references in tracked shell modules.

Works with sparse checkouts: both the reference scan and existence checks
read Git's tracked source tree, not the incomplete working directory.
Firmware-extracted inputs and variable paths are intentionally out of scope.
"""
import re
import subprocess
import sys
from pathlib import PurePosixPath


def git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True
    ).stdout


def tracked_paths() -> set[str]:
    return {
        p.decode("utf-8")
        for p in git("ls-files", "-z").split(b"\0")
        if p
    }


# All three types of prebuilt source are valid: files, split files, directories.
def exists(path: str, files: set[str]) -> bool:
    return (
        path in files
        or path + ".00" in files
        or any(p.startswith(path + "/") for p in files)
    )


def source_path(source: str, part: str, name: str, files: set[str]) -> str:
    base = "prebuilts/samsung/" + source
    if part == "system":
        if exists(base + "/system/system", files):
            return base + "/system/" + name
        return base + "/system/" + name.removeprefix("system/")
    if part == "system_ext":
        if exists(base + "/system_ext", files):
            return base + "/system_ext/" + name
        if exists(base + "/system/system/system_ext", files):
            return base + "/system/system/system_ext/" + name
        return base + "/system/system_ext/" + name
    return base + "/" + part + "/" + name


PATTERN = re.compile(
    r'\bADD_TO_WORK_DIR\s+"([A-Za-z0-9_]+)"\s+'
    r'"(system|system_ext|vendor|product|odm)"\s+"([^"]+)"'
)


def main() -> int:
    files = tracked_paths()
    errors: list[str] = []
    checked = 0
    scripts = sorted(path for path in files if path.endswith((".sh", ".bash")))
    for path in scripts:
        src = git("show", "HEAD:" + path).decode("utf-8-sig")
        # Support line-continuation between the three source arguments.
        src = src.replace("\\\n", "")
        for match in PATTERN.finditer(src):
            donor, part, name = match.groups()
            if "$" in name or name.startswith("/") or ".." in PurePosixPath(name).parts:
                # Variables are resolved at runtime from firmware or loops.
                continue
            line = src.count("\n", 0, match.start()) + 1
            reference = source_path(donor, part, name, files)
            checked += 1
            if not exists(reference, files):
                errors.append(f"{path}:{line}: missing prebuilt: {reference}")
    for error in errors:
        print("MISSING " + error, flush=True)
    print(f"Checked {checked} literal Samsung prebuilt references in "
          f"{len(scripts)} shell scripts; missing: {len(errors)}", flush=True)
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
