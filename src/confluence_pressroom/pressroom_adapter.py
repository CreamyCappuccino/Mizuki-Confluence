"""Actual Pressroom destination adapter composition for Confluence.

Imports Pressroom/SQLAlchemy only when instantiated. This lets the public repo's
offline tests exercise the provider core without pretending the local Pressroom
checkout is remotely reproducible.
"""
from __future__ import annotations

from pathlib import Path

from .provider_core import ConfluenceProviderCore, PublicAuthor, ResolvedArticle
from .staging import PrivateStagingStore


class _CanonicalReader:
    def __init__(self, session_factory) -> None:
        from pressroom.persistence import ManuscriptRepositoryProfile

        self._session_factory = session_factory
        self._profile = ManuscriptRepositoryProfile(destination_key="confluence")

    def get(self, ref: str, *, mode: str = "current") -> ResolvedArticle:
        from pressroom.persistence import (
            ManuscriptClassificationRepository,
            ManuscriptRepository,
            session_scope,
        )
        from pressroom.services.manuscript_projection import manuscript_snapshot

        with session_scope(self._session_factory) as session:
            record = ManuscriptRepository(session, profile=self._profile).get(ref, mode=mode)
            classification = ManuscriptClassificationRepository(
                session, profile=self._profile
            ).load(
                revision_id=record.revision.id,
                manuscript_id=record.manuscript.id,
                mode=mode,
            )
            snapshot = manuscript_snapshot(
                record,
                profile=self._profile,
                classification=classification,
            )
            authors = tuple(
                PublicAuthor(
                    author_ref=value.author_ref,
                    persona_name=value.persona_name,
                    harness=value.harness,
                    model=value.model,
                    role=value.role,
                    provenance_source=value.provenance_source,
                )
                for value in snapshot.authors
            )
            return ResolvedArticle(
                manuscript_id=record.manuscript.id,
                revision_id=record.revision.id,
                manuscript_ref=snapshot.manuscript_ref,
                revision_ref=snapshot.revision_ref,
                revision_no=snapshot.revision_no,
                edition_ref=snapshot.edition_ref,
                locale=snapshot.locale,
                title=snapshot.title,
                excerpt=snapshot.excerpt,
                author_label=snapshot.author_label,
                authors=authors,
                category_paths=snapshot.category_paths,
                tags=snapshot.tags,
                content_updated_at=snapshot.content_updated_at,
                rendered_html=snapshot.rendered_html,
                renderer_version=snapshot.renderer_version,
            )


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

        payload = dict(dispatch.payload_snapshot)
        selected = self._reader.get(str(payload["revision_ref"]))
        current = self._reader.get(selected.manuscript_ref)
        if selected.manuscript_id != dispatch.manuscript_id:
            raise ValueError("publication manuscript identity changed")
        if selected.revision_id != dispatch.revision_id:
            raise ValueError("publication revision identity changed")
        if current.revision_id != dispatch.revision_id:
            raise ValueError("manuscript changed after publication preview")
        if selected.revision_no != expected_revision:
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

        payload = dict(dispatch.payload_snapshot)
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

        result = self._staging.lookup(dispatch.action, dict(dispatch.payload_snapshot))
        return PublicationLookup(
            outcome=result.outcome,
            destination_ref=result.destination_ref,
            destination_url=result.destination_url,
            error_code=result.error_code,
            error_summary=result.error_summary,
        )
