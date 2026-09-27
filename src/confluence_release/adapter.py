"""Phase 1 preparation reused with AIL-style remote release composition."""
from __future__ import annotations
from .authority import CanonicalReleaseReader


class HereNowDestinationAdapter:
    key, display_name, adapter_kind = 'confluence', 'Confluence', 'confluence-here-now'

    def __init__(self, session_factory, config, *, delivery=None):
        from pressroom.destinations import DestinationCapabilities
        from confluence_pressroom.canonical_reader import _CanonicalReader
        from confluence_pressroom.provider_core import ConfluenceProviderCore
        self.config, self.delivery = config, delivery
        self.reader = _CanonicalReader(session_factory)
        self.authority = CanonicalReleaseReader(session_factory)
        self.core = ConfluenceProviderCore(self.reader, site_base_url=config.site_base)
        self.public_config = config.public_config
        # As in AIL: explicit durable APR is the approval. Adding an expiring
        # confirmation token here would strand queued JOBs after its TTL.
        self.capabilities = DestinationCapabilities(preview=True, publish=True, unpublish=True,
            external_side_effect=True, requires_two_step_approval=False,
            publication_mode='durable_release', pipeline_key=config.pipeline_key)

    def prepare(self, manuscript_ref, revision_ref, destination_metadata):
        from pressroom.destinations import PreparedPublication, PublicationPreview
        metadata = destination_metadata
        if metadata is None:
            day = self.authority.published_on(self.reader.get(manuscript_ref).manuscript_id)
            if day is not None:
                metadata = {'published_on': day}
        p = self.core.prepare(manuscript_ref, revision_ref, metadata)
        return PreparedPublication(manuscript_id=p.manuscript_id, revision_id=p.revision_id,
            preview=PublicationPreview(manuscript_ref=p.manuscript_ref, revision_ref=p.revision_ref,
                destination=self.key, destination_ref=p.destination_ref, destination_url=p.destination_url,
                title=p.title, payload_sha256=p.payload_sha256, requires_two_step_approval=False),
            payload_snapshot=p.payload_snapshot)

    def preview(self, manuscript_ref, revision_ref=None):
        return self.prepare(manuscript_ref, revision_ref, None).preview

    def resolve_manuscript_id(self, manuscript_ref):
        return self.reader.get(manuscript_ref).manuscript_id

    def publish(self, manuscript_ref, *, expected_revision, actor):
        raise ValueError('use PUB -> APR -> JOB, not direct publish')

    def unpublish(self, manuscript_ref, *, actor):
        raise ValueError('use PUB -> APR -> JOB, not direct unpublish')

    def status(self, manuscript_ref):
        return self.authority.status(manuscript_ref, self.reader)

    def _check_dispatch(self, dispatch, *, action=None, expected_revision=None):
        from confluence_pressroom.dispatch_validation import checked_payload, check_resolved_identity
        from confluence_pressroom.dispatch_validation import publish_revision_ref, withdrawal_manuscript_ref
        payload = checked_payload(dispatch, action=action)
        if dispatch.action == 'publish':
            selected = self.reader.get(publish_revision_ref(payload))
        else:
            withdrawal_manuscript_ref(payload)
            selected = self.reader.get(self.authority.revision_ref(dispatch.manuscript_id, dispatch.revision_id))
        check_resolved_identity(dispatch, selected, payload, site_base_url=self.config.site_base)
        if expected_revision is not None:
            if (type(expected_revision) is not int or selected.revision_no != expected_revision
                    or self.reader.get(selected.manuscript_ref).revision_id != dispatch.revision_id):
                raise ValueError('publication revision is stale')
        if self.delivery is None:
            raise ValueError('remote dispatch requires an approved JOB-bound delivery')
        self.delivery.check_dispatch(dispatch)
        return payload, selected

    def publish_dispatch(self, dispatch, *, expected_revision):
        payload, selected = self._check_dispatch(dispatch, action='publish', expected_revision=expected_revision)
        return self._deliver(dispatch, payload, selected)

    def unpublish_dispatch(self, dispatch):
        payload, selected = self._check_dispatch(dispatch, action='unpublish')
        return self._deliver(dispatch, payload, selected)

    def _deliver(self, dispatch, payload, selected):
        from pressroom.destinations import DestinationOutcomeUnknownError, PublicationResult
        try:
            self.delivery.perform(dispatch)
        except Exception as exc:
            # Delivery.perform begins only after local build, hash, identity and
            # configuration validation. It may have activated a remote version.
            raise DestinationOutcomeUnknownError('remote outcome not finalized; reconcile this JOB') from exc
        return PublicationResult(action=dispatch.action, manuscript_ref=selected.manuscript_ref,
            revision_ref=selected.revision_ref, destination=self.key,
            destination_ref=payload['destination_ref'], destination_url=payload['destination_url'],
            state='published' if dispatch.action == 'publish' else 'unpublished',
            publication_ref=dispatch.attempt_ref)

    def lookup_dispatch(self, dispatch):
        from pressroom.destinations import PublicationLookup
        try:
            payload, _ = self._check_dispatch(dispatch)
        except ValueError:
            return PublicationLookup(outcome='failed', error_code='invalid_dispatch',
                                     error_summary='approved dispatch identity/hash mismatch')
        try:
            if not self.delivery.lookup(dispatch):
                return PublicationLookup(outcome='unknown', error_summary='remote manifest is not confirmed')
        except Exception:
            return PublicationLookup(outcome='unknown', error_summary='remote readback unavailable')
        return PublicationLookup(outcome='succeeded', destination_ref=payload['destination_ref'],
                                 destination_url=payload['destination_url'])
