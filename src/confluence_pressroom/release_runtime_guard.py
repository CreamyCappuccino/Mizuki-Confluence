from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

RUNTIME_INPUTS = (
    "src/confluence_pressroom",
    "prototype",
    "tools",
    "pyproject.toml",
    "uv.lock",
)


class StaleReleaseRuntimeError(RuntimeError):
    """Raised before a stale long-lived worker can claim or publish a release."""


@dataclass(frozen=True, slots=True)
class ReleaseRuntimeGuard:
    project_root: Path
    source_commit: str

    @classmethod
    def capture(cls, project_root: Path) -> ReleaseRuntimeGuard:
        root = project_root.resolve()
        changes = _runtime_changes(root)
        if changes:
            raise StaleReleaseRuntimeError(
                "release runtime inputs are dirty before startup; commit or revert them: "
                + ", ".join(changes)
            )
        return cls(project_root=root, source_commit=_source_commit(root))

    def assert_current(self) -> None:
        changes = _runtime_changes(self.project_root)
        if changes:
            raise StaleReleaseRuntimeError(
                "release runtime inputs changed after startup; restart required: "
                + ", ".join(changes)
            )
        current_commit = _source_commit(self.project_root)
        if current_commit != self.source_commit:
            raise StaleReleaseRuntimeError(
                "release source commit changed after startup; restart required "
                f"({self.source_commit[:12]} -> {current_commit[:12]})"
            )


def _source_commit(project_root: Path) -> str:
    return _git(project_root, "rev-parse", "HEAD").strip()


def _runtime_changes(project_root: Path) -> tuple[str, ...]:
    output = _git(
        project_root,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        *RUNTIME_INPUTS,
    )
    return tuple(line[3:] for line in output.splitlines() if line.strip())


def _git(project_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout
