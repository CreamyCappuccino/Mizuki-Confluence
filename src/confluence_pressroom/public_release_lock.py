from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class PublicReleaseBusyError(RuntimeError):
    pass


@contextmanager
def public_release_lock(release_root: Path) -> Iterator[None]:
    """Serialize owner-only public mutations on this release host."""
    root = release_root.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".public-release.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PublicReleaseBusyError(
                "another Confluence public release is already in progress"
            ) from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = ["PublicReleaseBusyError", "public_release_lock"]
