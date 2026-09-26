"""Read-only preparation half of a future recoverable destination adapter.

Not a registry entry, live factory, publication adapter, or release worker.
PUB hashing/freezing and every write remain Pressroom's responsibility.
"""
from pathlib import Path
from .config import ConfluenceError, RehearsalConfig
from .dependency_pin import verify_local_dependencies
from .payload_schema import payload_sha256
from .ports import ManuscriptSource
from .preparation import prepare_payload


class PreparationProvider:
    """Exposes only prepare/resolve; deliberately cannot publish or unpublish."""
    key = "confluence"

    def __init__(self, config, source, evidence, prepared_type, preview_type):
        self.config, self.source, self.evidence = config, source, evidence
        self._prepared_type, self._preview_type = prepared_type, preview_type

    def prepare(self, manuscript_ref, revision_ref, destination_metadata, *, previous=None):
        resolved = self.source.resolve(manuscript_ref, revision_ref)
        snapshot = resolved.snapshot
        if snapshot.manuscript_ref != manuscript_ref or (
                revision_ref is not None and snapshot.revision_ref != revision_ref):
            raise ConfluenceError("source returned a different selected revision")
        if snapshot.renderer_version != self.evidence.renderer_version:
            raise ConfluenceError("revision renderer version needs an explicit compatibility review")
        payload = prepare_payload(resolved, destination_metadata, self.config, previous)
        preview = self._preview_type(
            manuscript_ref=snapshot.manuscript_ref, revision_ref=snapshot.revision_ref,
            destination=self.key, destination_ref=payload["destination_ref"],
            destination_url=payload["destination_url"], title=payload["title"],
            payload_sha256=payload_sha256(payload), requires_two_step_approval=True,
        )
        return self._prepared_type(resolved.manuscript_id, resolved.revision_id, preview, payload)

    def resolve_manuscript_id(self, manuscript_ref):
        resolved = self.source.resolve(manuscript_ref, None)
        if resolved.snapshot.manuscript_ref != manuscript_ref:
            raise ConfluenceError("source returned a different manuscript")
        return resolved.manuscript_id


def create_preparation_provider(config: RehearsalConfig, source: ManuscriptSource, *,
                                provenance: Path, pressroom_root: Path,
                                converter_root: Path) -> PreparationProvider:
    """Refuse absent/wrong actual dependencies before touching the source port.

    Do not register this partial object as RecoverableDestinationAdapter. Its
    dispatch/authority/storage/worker half is intentionally not yet supplied.
    """
    evidence = verify_local_dependencies(provenance, pressroom_root, converter_root)
    from pressroom.destinations.contracts import PreparedPublication, PublicationPreview
    return PreparationProvider(config, source, evidence, PreparedPublication, PublicationPreview)
