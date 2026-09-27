"""Synthetic release artifact helpers. No Pressroom/production connections."""
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

HTML = '<!doctype html><html><head><meta name="robots" content="noindex, nofollow, noarchive"></head><body><article>synthetic</article></body></html>'


def seal(root):
    paths = sorted(p for p in root.rglob("*") if p.is_file() and p.name != "checksums.sha256")
    raw = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}\n' for p in paths).encode()
    (root / 'checksums.sha256').write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def artifact(root):
    for relative, body in {
        'index.html': HTML, 'browse.html': HTML, 'ja/articles/art9001.html': HTML,
        'search.json': '{"entries":["synthetic"]}', 'robots.txt': 'User-agent: *\nAllow: /\n',
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')
    return seal(root)


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, text=True,
                          capture_output=True, check=True).stdout.strip()


def repository(root):
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'synthetic@example.invalid')
    git(root, 'config', 'user.name', 'Synthetic test')
    for relative in ['src/confluence_pressroom/worker.py', 'prototype/index.html',
                     'tools/build.py', 'pyproject.toml', 'uv.lock', 'docs/readme.md']:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# synthetic\n', encoding='utf-8')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'synthetic base')
