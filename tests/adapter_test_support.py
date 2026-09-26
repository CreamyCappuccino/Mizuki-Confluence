"""Offline Pressroom boundary doubles; not real DB/runtime compatibility evidence."""
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import UUID
import sys

from test_phase1_provider import FakeResolver, payload, resolved_article, unpublish_payload
from confluence_pressroom.payload import payload_sha256
from confluence_pressroom.pressroom_adapter import ConfluenceDestinationAdapter


def dispatch(action="publish", value=None):
    body = value if value is not None else (payload() if action == "publish" else unpublish_payload())
    return SimpleNamespace(
        action=action, destination_key="confluence", payload_snapshot=body,
        payload_sha256=payload_sha256(body), idempotency_key=f"fixture-{action}",
        manuscript_id=UUID("00000000-0000-0000-0000-000000000001"),
        revision_id=UUID("00000000-0000-0000-0000-000000000002"),
        attempt_ref="PUB99990001",
    )


def snapshot_files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@contextmanager
def pressroom_double(*, records=None, authors_by_revision=None):
    """Lazy-import doubles with the inspected repository's keyword signatures."""
    author_calls = []
    records = records or {}
    authors_by_revision = authors_by_revision or {}

    class Profile:
        def __init__(self, *, destination_key):
            self.destination_key = destination_key

    class Repository:
        def __init__(self, session, *, profile):
            self.profile = profile

        def get(self, ref, *, mode="current"):
            return records[ref]

    class Classification(Repository):
        def load(self, *, revision_id, manuscript_id, mode):
            return ()

    class Authors:
        def __init__(self, session, *, manuscript_profile=None):
            assert manuscript_profile.destination_key == "confluence"

        def list_many(self, revision_refs):
            author_calls.append(revision_refs)
            return {key: authors_by_revision[key] for key in revision_refs}

    def mod(name, **members):
        result = ModuleType(name)
        result.__path__ = []
        result.__dict__.update(members)
        return result

    modules = {
        "pressroom": mod("pressroom"),
        "pressroom.destinations": mod("pressroom.destinations",
            DestinationCapabilities=SimpleNamespace, PreparedPublication=SimpleNamespace,
            PublicationPreview=SimpleNamespace, PublicationResult=SimpleNamespace,
            PublicationStatus=SimpleNamespace, PublicationLookup=SimpleNamespace),
        "pressroom.domain": mod("pressroom.domain", PublicationStateError=RuntimeError),
        "pressroom.persistence": mod("pressroom.persistence",
            ManuscriptRepositoryProfile=Profile, ManuscriptRepository=Repository,
            ManuscriptClassificationRepository=Classification,
            AuthorIdentityRepository=Authors, session_scope=lambda factory: nullcontext(object())),
        "pressroom.persistence.author_repository": mod("pressroom.persistence.author_repository",
            AuthorIdentityRepository=Authors),
        "pressroom.services": mod("pressroom.services"),
        "pressroom.services.manuscript_projection": mod("pressroom.services.manuscript_projection",
            manuscript_snapshot=lambda record, **kwargs: record.snapshot),
    }
    with patch.dict(sys.modules, modules):
        yield author_calls


def make_adapter(root):
    result = ConfluenceDestinationAdapter(None, staging_root=Path(root) / "staging",
                                         site_base_url="https://confluence.invalid")
    result._reader = FakeResolver(resolved_article())
    return result
