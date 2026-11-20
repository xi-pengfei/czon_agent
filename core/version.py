"""Identify the installed application, excluding customer data and skills."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = ['core', 'adapters', 'tools_builtin', 'webui', 'main.py', 'requirements.txt', 'VERSION']


def version_info(root=ROOT):
    root = Path(root)
    version = (root / 'VERSION').read_text(encoding='utf-8').strip() if (root / 'VERSION').exists() else 'unversioned'
    manifest = root / '.release.json'
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding='utf-8'))
        modified = False
        for name, expected in data['files'].items():
            path = root / name
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('Invalid release manifest path')
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                modified = True
        return {'version': version, 'revision': data['revision'], 'installed_at': data.get('installed_at', ''), 'modified': modified, 'source': 'release'}
    try:
        def git(*args):
            return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL, timeout=5).decode().strip()
        revision = git('rev-parse', 'HEAD')
        modified = bool(git('status', '--porcelain', '--untracked-files=normal', '--', *RUNTIME_PATHS))
    except (OSError, subprocess.SubprocessError):
        revision, modified = 'unknown', True
    return {'version': version, 'revision': revision, 'installed_at': '', 'modified': modified, 'source': 'checkout'}
