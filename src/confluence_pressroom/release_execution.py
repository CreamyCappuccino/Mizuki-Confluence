"""Thin synchronous AIL-shaped safety envelope; not a JOB store or daemon.

The caller supplies Pressroom claim/build/deliver/readback/finalize operations.
Exceptions propagate so the existing durable recovery policy retains authority.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from .public_release_lock import public_release_lock
from .release_runtime_guard import ReleaseRuntimeGuard

Context = TypeVar("Context")
Artifact = TypeVar("Artifact")
Receipt = TypeVar("Receipt")
Evidence = TypeVar("Evidence")
Result = TypeVar("Result")


def run_guarded_release(
    *,
    guard: ReleaseRuntimeGuard,
    release_root: Path,
    claim: Callable[[], Context | None],
    build: Callable[[Context], Artifact],
    deliver: Callable[[Context, Artifact], Receipt],
    readback: Callable[[Context, Artifact, Receipt], Evidence],
    finalize: Callable[[Context, Evidence], Result],
) -> Result | None:
    """Never claim while busy/stale; never finalize without successful readback.

    Use one stable site-level release_root for every publisher/reconciler on
    this host. Snapshot/binding checks stay inside the supplied operations.
    No exception is converted to success, and delivery is never auto-retried.
    """
    guard.assert_current()
    with public_release_lock(release_root):
        guard.assert_current()
        context = claim()
        if context is None:
            return None
        guard.assert_current()
        artifact = build(context)
        guard.assert_current()
        receipt = deliver(context, artifact)
        guard.assert_current()
        evidence = readback(context, artifact, receipt)
        guard.assert_current()
        return finalize(context, evidence)
