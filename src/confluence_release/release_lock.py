"""AIL bd69012 public_release_lock.py with Confluence naming only."""
from __future__ import annotations
import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class PublicReleaseBusyError(RuntimeError):
    pass


@contextmanager
def public_release_lock(release_root: Path) -> Iterator[None]:
    """Serialize public mutations on this release host, including presentation."""
    root = release_root.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.public-release.lock').open('a+', encoding='utf-8') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PublicReleaseBusyError('another Confluence release is in progress') from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
