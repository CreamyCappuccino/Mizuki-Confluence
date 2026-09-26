"""Authoritative Pressroom reads are injected; the destination never edits originals."""
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class ResolvedManuscript:
    manuscript_id: UUID
    revision_id: UUID
    snapshot: Any  # Actual pressroom.domain.ManuscriptSnapshot, not a serialized actor.


@dataclass(frozen=True)
class BindingView:
    """Read from Confluence's canonical Pressroom binding, not snapshot.is_published."""
    state: str
    published_revision_ref: str | None = None
    destination_url: str | None = None


class ManuscriptSource(Protocol):
    def resolve(self, manuscript_ref: str, revision_ref: str | None) -> ResolvedManuscript: ...
    def resolve_ids(self, manuscript_id: UUID, revision_id: UUID) -> ResolvedManuscript: ...
    def binding(self, manuscript_ref: str, destination_key: str) -> BindingView: ...


class DispatchAuthority(Protocol):
    def hold(self, dispatch: Any, *, expected_revision: int | None, recover: bool = False) -> AbstractContextManager:
        """Hold the canonical per-binding publication lock.

        Verify approved APR/JOB, exact payload/revision/destination/config,
        current revision for publish, and published revision for withdrawal.
        The lock must remain held through activation/readback. Replay/recovery
        policy belongs to the canonical ledger, not to public HTML or this port.
        An arbitrary duck-typed dispatch is NOT authority.
        """
        ...
