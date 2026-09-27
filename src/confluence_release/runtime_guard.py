"""Adapted from AIL bd69012 release_runtime_guard.py (source read over Relay)."""
from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path

RUNTIME_INPUTS = ('src/confluence_pressroom', 'src/confluence_release',
                  'prototype/assets', 'pyproject.toml', 'uv.lock')


class StaleReleaseRuntimeError(RuntimeError):
    """An old process must not publish a newer checkout with mixed code/assets."""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(['git', *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout


def _changes(root: Path) -> tuple[str, ...]:
    output = _git(root, 'status', '--porcelain', '--untracked-files=all', '--', *RUNTIME_INPUTS)
    return tuple(line[3:] for line in output.splitlines() if line.strip())


@dataclass(frozen=True)
class ReleaseRuntimeGuard:
    project_root: Path
    source_commit: str

    @classmethod
    def capture(cls, root: Path):
        root = root.resolve()
        if _changes(root):
            raise StaleReleaseRuntimeError('release inputs are dirty; commit before starting the worker')
        return cls(root, _git(root, 'rev-parse', 'HEAD').strip())

    def assert_current(self):
        if _changes(self.project_root):
            raise StaleReleaseRuntimeError('release inputs changed; restart the worker')
        if _git(self.project_root, 'rev-parse', 'HEAD').strip() != self.source_commit:
            raise StaleReleaseRuntimeError('release checkout changed; restart the worker')
