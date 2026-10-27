#!/usr/bin/env python3
"""Build the bundled Apple Translation helper for Intel and Apple silicon."""
from pathlib import Path
import subprocess
import tempfile


def build():
    root = Path(__file__).resolve().parents[1]
    destination = root / 'bin' / 'apple-translate'
    destination.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='iciba-native-') as directory:
        directory = Path(directory)
        slices = []
        for arch in ('arm64', 'x86_64'):
            output = directory / arch
            subprocess.run([
                'xcrun', 'swiftc', '-parse-as-library', '-O',
                '-target', arch + '-apple-macos26.0',
                str(root / 'native' / 'AppleTranslate.swift'), '-o', str(output),
            ], check=True)
            slices.append(str(output))
        universal = directory / 'apple-translate'
        subprocess.run(['xcrun', 'lipo', '-create', *slices, '-output', str(universal)],
                       check=True)
        subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-',
                        '--timestamp=none', str(universal)], check=True)
        destination.write_bytes(universal.read_bytes())
        destination.chmod(0o755)
    print(destination)


if __name__ == '__main__':
    build()
