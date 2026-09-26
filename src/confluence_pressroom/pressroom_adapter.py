"""Actual Pressroom destination adapter composition for Confluence.

Imports Pressroom/SQLAlchemy only when instantiated. This lets the public repo's
offline tests exercise the provider core without pretending the local Pressroom
checkout is remotely reproducible.
"""
from __future__ import annotations

from pathlib import Path

from .canonical_reader import _CanonicalReader
from .dispatch_validation import (
    check_resolved_identity, checked_payload, publish_revision_ref, withdrawal_manuscript_ref,
)
from .provider_core import ConfluenceProviderCore
from .staging import PrivateStagingStore


class ConfluenceDestinationAdapter:
    key = "confluence"
    display_name = "Confluence"
    adapter_kind = "confluence-static"

    def __init__(
        self,
        session_factory,
        *,
        staging_root: str | Path,
        site_base_url: str,
    ) -> None:
        from pressroom.destinations import DestinationCapabilities

        self._site_base_url = site_base_url
        self.public_config = {
            "site_base_url": site_base_url,
            "external_discovery": "discouraged",
            "robots": "noindex, nofollow, noarchive",
            "sitemap": False,
        }
        self.capabilities = DestinationCapabilities(
            preview=True,
            publish=True,
            unpublish=True,
            external_side_effect=True,
            requires_two_step_approval=True,
            publication_mode="durable_release",
            pipeline_key="confluence-staging-v1",
        )
        self._reader = _CanonicalReader(session_factory)
        self._core = ConfluenceProviderCore(self._reader, site_base_url=site_base_url)
        self._staging = PrivateStagingStore(staging_root)

    def preview(self, manuscript_ref: str, revision_ref: str | None):
        raise ValueError("Confluence preview requires destination_metadata.published_on")

    def prepare(self, manuscript_ref: str, revision_ref: str | None, destination_metadata):
        from pressroom.destinations import PreparedPublication, PublicationPreview

        metadata = destination_metadata
        if metadata is None:
            existing_date = self._staging.published_on(manuscript_ref)
            if existing_date is not None:
                metadata = {"published_on": existing_date}
        prepared = self._core.prepare(manuscript_ref, revision_ref, metadata)
        return PreparedPublication(
            manuscript_id=prepared.manuscript_id,
            revision_id=prepared.revision_id,
            preview=PublicationPreview(
                manuscript_ref=prepared.manuscript_ref,
                revision_ref=prepared.revision_ref,
                destination=self.key,
                destination_ref=prepared.destination_ref,
                destination_url=prepared.destination_url,
                title=prepared.title,
                payload_sha256=prepared.payload_sha256,
                requires_two_step_approval=True,
            ),
            payload_snapshot=prepared.payload_snapshot,
        )

    def resolve_manuscript_id(self, manuscript_ref: str):
        return self._reader.get(manuscript_ref).manuscript_id

    def publish(self, manuscript_ref: str, *, expected_revision: int, actor):
        from pressroom.domain import PublicationStateError

        del manuscript_ref, expected_revision, actor
        raise PublicationStateError(
            "Confluence publication requires PUB/APR/JOB durable release"
        )

    def publish_dispatch(self, dispatch, *, expected_revision: int):
        from pressroom.destinations import PublicationResult

        payload = checked_payload(dispatch, action="publish")
        selected = self._reader.get(publish_revision_ref(payload))
        check_resolved_identity(dispatch, selected, payload, site_base_url=self._site_base_url)
        current = self._reader.get(selected.manuscript_ref)
        if current.revision_id != dispatch.revision_id:
            raise ValueError("manuscript changed after publication preview")
        if type(expected_revision) is not int or selected.revision_no != expected_revision:
            raise ValueError("revision_ref and expected_revision mismatch")
        receipt = self._staging.publish(payload, idempotency_key=dispatch.idempotency_key)
        return PublicationResult(
            action="publish",
            manuscript_ref=receipt.manuscript_ref,
            revision_ref=receipt.revision_ref,
            destination=self.key,
            destination_ref=receipt.destination_ref,
            destination_url=receipt.destination_url,
            state="published",
            publication_ref=dispatch.attempt_ref,
        )

    def unpublish(self, manuscript_ref: str, *, actor):
        from pressroom.domain import PublicationStateError

        del manuscript_ref, actor
        raise PublicationStateError(
            "Confluence unpublish requires PUB/APR/JOB durable release"
        )

    def unpublish_dispatch(self, dispatch):
        from pressroom.destinations import PublicationResult

        payload = checked_payload(dispatch, action="unpublish")
        selected = self._withdrawal_revision(payload)
        check_resolved_identity(dispatch, selected, payload, site_base_url=self._site_base_url)
        receipt = self._staging.unpublish(payload, idempotency_key=dispatch.idempotency_key)
        return PublicationResult(
            action="unpublish",
            manuscript_ref=receipt.manuscript_ref,
            revision_ref=receipt.revision_ref,
            destination=self.key,
            destination_ref=receipt.destination_ref,
            destination_url=receipt.destination_url,
            state="unpublished",
            publication_ref=dispatch.attempt_ref,
        )

    def status(self, manuscript_ref: str):
        from pressroom.destinations import PublicationStatus

        current = self._reader.get(manuscript_ref)
        published = self._staging.published_payload(manuscript_ref)
        return PublicationStatus(
            manuscript_ref=current.manuscript_ref,
            destination=self.key,
            state="published" if published is not None else "unpublished",
            current_revision_ref=current.revision_ref,
            published_revision_ref=(str(published["revision_ref"]) if published else None),
            destination_url=(str(published["destination_url"]) if published else None),
        )

    def lookup_dispatch(self, dispatch):
        from pressroom.destinations import PublicationLookup

        try:
            payload = checked_payload(dispatch)
            selected = (self._reader.get(publish_revision_ref(payload))
                        if dispatch.action == "publish" else self._withdrawal_revision(payload))
            check_resolved_identity(dispatch, selected, payload, site_base_url=self._site_base_url)
            self._staging.check_operation_identity(
                dispatch.action, payload, idempotency_key=dispatch.idempotency_key
            )
        except _MissingWithdrawalEvidence:
            return PublicationLookup(outcome="unknown", error_summary="withdrawal identity evidence unavailable")
        except ValueError:
            return PublicationLookup(outcome="failed", error_code="invalid_dispatch",
                                     error_summary="dispatch identity or approved hash mismatch")
        result = self._staging.lookup(dispatch.action, payload)
        return PublicationLookup(
            outcome=result.outcome,
            destination_ref=result.destination_ref,
            destination_url=result.destination_url,
            error_code=result.error_code,
            error_summary=result.error_summary,
        )

    def _withdrawal_revision(self, payload):
        ref = withdrawal_manuscript_ref(payload)
        known = self._staging.publication_identity(ref)
        if known is None or not isinstance(known.get("revision_ref"), str):
            # Do not infer a removed revision from the current draft. History
            # is private reconciliation evidence, never a second manuscript DB.
            raise _MissingWithdrawalEvidence("withdrawal identity evidence unavailable")
        for field in ("destination_ref", "destination_url"):
            if payload.get(field) != known.get(field):
                raise ValueError("unpublish target changed from known publication")
        return self._reader.get(known["revision_ref"])


class _MissingWithdrawalEvidence(RuntimeError):
    """No exact revision/route evidence; recovery must remain unknown."""
