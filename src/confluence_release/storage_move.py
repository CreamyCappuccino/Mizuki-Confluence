"""Filesystem-only verified copies and optional archival; no runtime/DB activation."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from uuid import uuid4

from .artifact_location import absolute_path, real_directory, record_digest

FORMAT = 'confluence-storage-copy/v1'


def _file_digest(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('storage copy accepts regular files only')
        h = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('storage file changed during inventory')
        return h


def inventory(root: Path) -> dict:
    real_directory(root)
    result = {}
    def walk(folder):
        real_directory(folder)
        for p in sorted(folder.iterdir()):
            info = p.lstat()
            if info.st_uid != os.getuid():
                raise ValueError('storage contains a different owner')
            rel = p.relative_to(root).as_posix()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISDIR(info.st_mode):
                result[rel] = dict(type='dir', mode=mode)
                walk(p)
            elif stat.S_ISREG(info.st_mode):
                result[rel] = dict(type='file', mode=mode, size=info.st_size, sha256=_file_digest(p))
            else:
                raise ValueError('storage links and special files are not portable evidence')
    walk(root)
    return result


def _git(project: Path, *args) -> str:
    return subprocess.run(['git', '-C', str(project), *args], check=True,
        capture_output=True, text=True, timeout=20).stdout.strip()


def _project(project: Path) -> None:
    real_directory(project)
    if project.stat().st_uid != os.getuid() or Path(_git(project, 'rev-parse', '--show-toplevel')) != project:
        raise ValueError('destination must be the existing owner-owned project Git root')


def _ignored(project: Path, relative: str) -> None:
    probe = relative.rstrip('/') + '/__confluence_private_probe__'
    if _git(project, 'ls-files', '--', relative):
        raise ValueError('private destination includes Git-tracked files')
    _git(project, 'check-ignore', '--no-index', '--', probe)


def _private_parents(project: Path, parent: Path) -> None:
    relative = parent.relative_to(project)
    current = project
    for part in relative.parts:
        current /= part
        if not current.exists(): current.mkdir(mode=0o700)
        real_directory(current)
        if current.stat().st_uid != os.getuid() or stat.S_IMODE(current.stat().st_mode) != 0o700:
            raise ValueError('private destination directory must be owner-only 0700')


def layout(source: Path) -> list[tuple[Path, str]]:
    """Unknown entries are surfaced rather than discarded or copied elsewhere."""
    result = []
    for p in sorted(source.iterdir()):
        name = p.name
        if name == 'source': target = 'runtime/source'
        elif name in {'releases', 'checkpoints'}: target = name
        elif name.startswith('acceptance-'): target = 'evidence/' + name
        else: raise ValueError('unexpected old storage entry; review inventory first')
        real_directory(p)
        result.append((p, target))
    if not result: raise ValueError('old storage is empty')
    return result


def plan_copy(source: Path, project: Path, *, require_empty: bool = True) -> dict:
    source, project = absolute_path(str(source)), absolute_path(str(project))
    real_directory(source); _project(project)
    if source.stat().st_uid != os.getuid():
        raise ValueError('source storage must be owned by the operator')
    if source == project or source in project.parents or project in source.parents:
        raise ValueError('source and project must be disjoint trees')
    moves = []
    for old, relative in layout(source):
        destination = project / relative
        parent = destination.parent
        while not parent.exists() and not parent.is_symlink():
            parent = parent.parent
        real_directory(parent)
        _ignored(project, relative)
        if require_empty and (destination.exists() or destination.is_symlink()):
            raise ValueError('destination already exists; never overwrite')
        moves.append(dict(source=str(old), target=relative, inventory=inventory(old)))
    payload = dict(format=FORMAT, source=str(source), project=str(project), moves=moves)
    return dict(payload, fingerprint=record_digest(payload))


@contextmanager
def migration_lock(project: Path):
    """Serialize this operator tool; local cutover must separately quiesce writers."""
    _project(project)
    gitdir = Path(_git(project, 'rev-parse', '--absolute-git-dir'))
    real_directory(gitdir)
    fd = os.open(gitdir/'confluence-storage-migration.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def _copy_file(source: Path, target: Path, mode: int) -> None:
    src = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(src, 'rb') as incoming:
        if not stat.S_ISREG(os.fstat(incoming.fileno()).st_mode):
            raise ValueError('copy source became non-regular')
        out = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(out, 'wb') as outgoing:
            shutil.copyfileobj(incoming, outgoing)
            outgoing.flush(); os.fsync(outgoing.fileno()); os.fchmod(outgoing.fileno(), mode)


def _copy_tree(old: Path, destination: Path, entries: dict) -> None:
    stage = destination.with_name(destination.name + '-copying-' + uuid4().hex)
    stage.mkdir(mode=0o700)
    try:
        for relative, entry in entries.items():
            target = stage / relative
            if entry['type'] == 'dir': target.mkdir(mode=0o700)
            else: _copy_file(old/relative, target, entry['mode'])
        for relative, entry in reversed(list(entries.items())):
            if entry['type'] == 'dir': (stage/relative).chmod(entry['mode'])
        if inventory(stage) != entries or inventory(old) != entries:
            raise ValueError('source or verified copy changed; originals retained')
        if destination.exists() or destination.is_symlink():
            raise ValueError('target appeared during copy; never overwrite')
        stage.rename(destination)
    except BaseException:
        # All content here is our temporary copy, never the original source.
        if stage.exists(): shutil.rmtree(stage)
        raise


def write_receipt(project: Path, path: Path, values: dict) -> str:
    path = absolute_path(str(path))
    relative = path.relative_to(project)
    if relative.parts[:2] != ('checkpoints', 'path-migration'):
        raise ValueError('migration receipts belong in project checkpoints/path-migration')
    _ignored(project, relative.parent.as_posix())
    _private_parents(project, path.parent)
    raw = (json.dumps(values, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw); out.flush(); os.fsync(out.fileno())
    return hashlib.sha256(raw).hexdigest()


def copy_storage(source: Path, project: Path, *, expected_fingerprint: str, receipt_path: Path) -> dict:
    with migration_lock(project):
        rel = absolute_path(str(receipt_path)).relative_to(project)
        if rel.parts[:2] != ('checkpoints', 'path-migration'):
            raise ValueError('copy receipt must be in project migration checkpoints')
        plan = plan_copy(source, project)
        if plan['fingerprint'] != expected_fingerprint:
            raise ValueError('source inventory changed since reviewed plan')
        if receipt_path.exists() or receipt_path.is_symlink():
            raise ValueError('receipt already exists; inspect previous run')
        for move in plan['moves']:
            target = project/move['target']
            _private_parents(project, target.parent)
            _copy_tree(Path(move['source']), target, move['inventory'])
        result = dict(plan, status='COPIED_NOT_ACTIVATED')
        result['receipt_sha256'] = write_receipt(project, receipt_path, result)
        return result


def _verify_targets(plan: dict, *, executing_source_sha: str | None = None) -> None:
    project = Path(plan['project'])
    for move in plan['moves']:
        target = project/move['target']; real_directory(target)
        if move['target'] == 'runtime/source' and executing_source_sha is not None:
            if (not re.fullmatch(r'[0-9a-f]{40}', executing_source_sha)
                    or _git(target, 'rev-parse', 'HEAD') != executing_source_sha
                    or _git(target, 'status', '--porcelain', '--untracked-files=all')):
                raise ValueError('relocated executing source is not exact/clean')
            continue
        actual = inventory(target)
        if move['target'] == 'checkpoints':
            # Only newly created migration records may supplement the copied checkpoints.
            if any(p == 'path-migration' or p.startswith('path-migration/') for p in move['inventory']):
                raise ValueError('reserved migration checkpoint already existed in old store')
            actual = {p: v for p, v in actual.items() if p != 'path-migration' and not p.startswith('path-migration/')}
        if actual != move['inventory']:
            raise ValueError('copied data changed before archival')


def archive_source(plan: dict, *, archive: Path, executing_source_sha: str | None = None) -> None:
    """Called ONLY after owner-confirmed cutover; rename, never delete old data."""
    source, project = Path(plan['source']), Path(plan['project'])
    with migration_lock(project):
        current = plan_copy(source, project, require_empty=False)
        if (current['fingerprint'] != plan['fingerprint']
                or any(current[k] != plan[k] for k in ('format', 'source', 'project', 'moves'))):
            raise ValueError('old source changed since copy; do not archive')
        relative = absolute_path(str(archive)).relative_to(project)
        if relative.parts[:2] != ('checkpoints', 'path-migration') or len(relative.parts) < 3:
            raise ValueError('archive must be inside project migration checkpoints')
        _verify_targets(plan, executing_source_sha=executing_source_sha)
        _private_parents(project, archive.parent)
        if archive.exists() or archive.is_symlink(): raise ValueError('archive already exists')
        if source.stat().st_dev != archive.parent.stat().st_dev:
            raise ValueError('archive requires same filesystem; no delete fallback')
        source.rename(archive)
