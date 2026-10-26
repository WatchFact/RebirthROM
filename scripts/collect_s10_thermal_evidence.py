#!/usr/bin/env python3
"""Preserve bounded S10 thermal-policy evidence; never invent or alter policy."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

out, dest = map(Path, sys.argv[1:])
dest.mkdir(parents=True, exist_ok=True)
manifest = []
# Only target-stock S10 policies, not generic donor device thermal data.
for apk in (out / 'fw').glob('SM-G97*/system/system/priv-app/SamsungDeviceHealthManagerService/*.apk'):
    try:
        with zipfile.ZipFile(apk) as z:
            for item in z.infolist():
                name = Path(item.filename).name
                if not (name.startswith('siop_beyond') and 'exynos9820' in name and name.endswith('.xml')):
                    continue
                if item.file_size > 1024 * 1024:
                    continue
                data = z.read(item)
                label = apk.parts[apk.parts.index('fw') + 1] + '-' + name
                (dest / label).write_bytes(data)
                manifest.append({'source': str(apk), 'entry': item.filename,
                                 'sha256': hashlib.sha256(data).hexdigest(), 'output': label})
    except (OSError, zipfile.BadZipFile) as exc:
        manifest.append({'source': str(apk), 'error': str(exc)})
base = out / 'target/beyond2lte/apktool/system/priv-app/SamsungDeviceHealthManagerService/SamsungDeviceHealthManagerService.apk'
for path in sorted(base.glob('assets/*')):
    if path.is_file() and path.name.startswith(('siop', 'ssrm')):
        data = path.read_bytes()
        manifest.append({'source': str(path), 'size': len(data),
                         'sha256': hashlib.sha256(data).hexdigest(), 'first32hex': data[:32].hex()})
# Parser source is evidence for a reviewed adapter, not proof of compatibility.
count = 0
for path in sorted(base.glob('smali*/**/*.smali')):
    if count >= 40 or path.stat().st_size > 512 * 1024:
        continue
    data = path.read_bytes()
    if any(key in data for key in (b'"siop_document"', b'"siop_model"', b'"ssrm_default"')):
        target = dest / 'parser' / path.relative_to(base)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        count += 1
(dest / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(f'Collected {len(manifest)} thermal evidence records and {count} parser files')
