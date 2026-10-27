#!/usr/bin/env python3
"""Build the installable workflow from an explicit set of runtime files."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def build():
    root = Path(__file__).resolve().parents[1]
    files = [root / name for name in ('iciba.py', 'info.plist', 'icon.png')]
    files.extend(sorted((root / 'alfred').glob('*.py')))
    destination = root / 'bundle' / 'iciba.alfredworkflow'
    destination.parent.mkdir(exist_ok=True)
    with ZipFile(destination, 'w') as archive:
        for path in files:
            entry = ZipInfo(path.relative_to(root).as_posix())
            entry.compress_type = ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, path.read_bytes())
    print(destination)


if __name__ == '__main__':
    build()
